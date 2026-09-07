import re
from pathlib import Path
from datetime import date
import openpyxl
import json
from utils.text_utils import TextUtils
from typing import List, Tuple, Optional, Set, Dict, Any
from utils.excel_helper import ExcelHelper

# Предполагаем, что models.py содержит классы SupplyItem и Candidate.
# Если нет – можно определить их прямо здесь, но по заданию они в отдельном файле.
from models.models import SupplyItem, Candidate   # или из .models import ...

# Вспомогательные утилиты (можно использовать существующие ExcelHelper, FileHelper)
# Но для простоты используем прямо openpyxl и стандартные средства.


class DataLoader:
    """Загрузка данных из подготовленных Excel-файлов."""

    def __init__(self, brands_set: Set[str] = None, log_callback=None):
        self.brands_set = brands_set or set()
        self.log = log_callback or print

    @staticmethod
    def _find_header_row_and_columns(sheet, header_variants: dict, max_rows=15, max_cols=20) -> tuple:
        """
        Ищет строку с заголовками и возвращает (row_index, column_indices).
        header_variants: dict {поле: [варианты_заголовков]}
        Возвращает (row_index, dict) или (None, None)
        """
        all_variants = {}
        for field, variants in header_variants.items():
            for v in variants:
                all_variants[v.lower().strip()] = field

        best_score = 0
        best_row = None
        best_columns = {}

        for row_idx in range(1, min(sheet.max_row, max_rows) + 1):
            header_row = list(sheet.iter_rows(min_row=row_idx, max_row=row_idx, values_only=True))[0]
            if not header_row:
                continue
            header_row = header_row[:max_cols]  # ограничиваем количество столбцов

            found_columns = {}
            score = 0
            for col_idx, cell in enumerate(header_row):
                if cell is None:
                    continue
                cell_clean = str(cell).strip().lower()
                if cell_clean in all_variants:
                    field = all_variants[cell_clean]
                    if field not in found_columns:
                        found_columns[field] = col_idx
                        score += 1

            # Если нашли все обязательные поля (name и shk, либо name и count) – сразу принимаем
            # Для файлов поставок обязательные: name, shk, serial (но serial опционален)
            # Для сборного файла обязательные: name, shk (или count)
            # Проверяем наличие name и shk (или name и count)
            if 'name' in found_columns and 'shk' in found_columns:
                return row_idx, found_columns
            if 'name' in found_columns and 'count' in found_columns:
                return row_idx, found_columns

            if score > best_score:
                best_score = score
                best_row = row_idx
                best_columns = found_columns

        if best_row is None or best_score < 2:
            return None, None
        # Проверяем наличие обязательного поля name
        if 'name' not in best_columns:
            return None, None
        return best_row, best_columns

    def load_supply_items(self, file_path: Path) -> List[SupplyItem]:
        self.log(f"Загрузка товаров из листа поставки: {file_path.name}")
        items = []
        try:
            wb = ExcelHelper.open_data_file(file_path, read_only=True, data_only=True)
            ws = wb.active

            # Определяем варианты заголовков
            header_variants = {
                'article': ["Артикул", "SKU", "Article", "Код", "Product code"],
                'name': ["Наименование", "Name", "Product name", "Description", "Товар"],
                'count': ["Количество", "Quantity", "Qty", "Кол-во"],
                'row_num': ["№", "№ п/п", "№ п.п.", "Номер", "Item", "Row"]
            }

            header_row, columns = self._find_header_row_and_columns(ws, header_variants)
            if header_row is None or columns is None:
                self.log("Не удалось найти заголовки таблицы. Проверьте структуру файла.")
                wb.close()
                return []

            self.log(f"Заголовки найдены в строке {header_row}")
            self.log(
                f"Столбцы: артикул={columns.get('article')}, наименование={columns.get('name')}, количество={columns.get('count')}, №={columns.get('row_num')}")

            col_article = columns.get('article')
            col_name = columns.get('name')
            col_count = columns.get('count')
            col_row_num = columns.get('row_num')

            # Читаем данные, начиная со следующей строки
            for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                if col_name is None or len(row) <= col_name or not row[col_name]:
                    continue
                name_str = str(row[col_name]).strip()
                if not name_str or name_str.lower() == 'наименование':
                    continue

                article = row[col_article] if col_article is not None and len(row) > col_article else ""
                count_raw = row[col_count] if col_count is not None and len(row) > col_count else None
                count = None
                if count_raw is not None:
                    try:
                        count = int(float(count_raw))
                    except (ValueError, TypeError):
                        count = None

                row_num = row[col_row_num] if col_row_num is not None and len(row) > col_row_num else None

                features = self._extract_features(name_str, self.brands_set)
                items.append(SupplyItem(
                    row_num=row_num,
                    article=str(article).strip() if article else "",
                    name=name_str,
                    count=count,
                    keywords=features['keywords'],
                    brand=features['brand']
                ))
            wb.close()
        except Exception as e:
            self.log(f"Ошибка загрузки листа поставки: {e}")
            raise
        self.log(f"Загружено товаров: {len(items)}")
        if items:
            self.log("Первые 5 товаров (имя, количество):")
            for i, item in enumerate(items[:5]):
                self.log(f"  {i + 1}. {item.name} | кол-во: {item.count} | keywords: {item.keywords}")
        return items

    def load_candidates(self, file_path: Path) -> List[Candidate]:
        self.log(f"Загрузка кандидатов из сборного файла: {file_path.name}")
        candidates = []
        try:
            wb = ExcelHelper.open_data_file(file_path, read_only=True, data_only=True)
            ws = wb.active

            # Варианты заголовков для сборного файла
            header_variants = {
                'name': ["Наименование", "Name"],
                'count': ["Количество_строк", "Количество строк", "Count", "Quantity", "Количество"],
                'serial': ["Серийный_номер", "Serial number"],
                'source_file': ["Файл_источник", "Source file"],
                'shk': ["ШК", "GTIN", "Barcode"]
            }

            header_row, columns = self._find_header_row_and_columns(ws, header_variants)
            if header_row is None or columns is None:
                self.log("Не удалось найти заголовки в сборном файле.")
                wb.close()
                return []

            col_name = columns.get('name')
            col_count = columns.get('count')
            col_serial = columns.get('serial')
            col_source = columns.get('source_file')
            col_shk = columns.get('shk')

            if col_name is None or col_shk is None:
                self.log("В сборном файле не найдены столбцы 'Наименование' или 'ШК'.")
                wb.close()
                return []

            for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                name = row[col_name] if col_name is not None and len(row) > col_name else None
                if not name:
                    continue
                count = row[col_count] if col_count is not None and len(row) > col_count else None
                if count is not None:
                    try:
                        count = int(count)
                    except (ValueError, TypeError):
                        count = None
                serial = row[col_serial] if col_serial is not None and len(row) > col_serial else None
                source_file = row[col_source] if col_source is not None and len(row) > col_source else ""
                shk = row[col_shk] if col_shk is not None and len(row) > col_shk else None

                features = self._extract_features(str(name).strip(), self.brands_set)
                candidates.append(Candidate(
                    name=str(name).strip(),
                    count=count,
                    serial=str(serial).strip() if serial else None,
                    source_file=str(source_file).strip() if source_file else "",
                    keywords=features['keywords'],
                    brand=features['brand'],
                    shk=str(shk).strip() if shk else None
                ))
            wb.close()
        except Exception as e:
            self.log(f"Ошибка загрузки сборного файла: {e}")
            raise
        self.log(f"Загружено кандидатов: {len(candidates)}")
        if candidates:
            self.log("Первые 5 кандидатов с ключевыми словами:")
            for i, cand in enumerate(candidates[:5]):
                self.log(f"  {i+1}. {cand.name} -> keywords: {cand.keywords}")
        return candidates

    def load_csv_via_normalizer(self, file_path: Path) -> List[Dict[str, str]]:
        """Загружает CSV-файл через нормализатор по строкам."""
        from utils.excel_helper import CsvNormalizer
        normalizer = CsvNormalizer(file_path)
        valid_rows, invalid_log = normalizer.normalize_rows(self.log)

        if invalid_log:
            log_path = Path(file_path).parent / f"log_некорректные_строки_{Path(file_path).stem}.txt"
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"Некорректные строки в файле {Path(file_path).name}\n")
                f.write("=" * 60 + "\n")
                for line in invalid_log:
                    f.write(line + "\n")
            self.log(f"  Некорректные строки сохранены в {log_path.name}")

        return valid_rows

    @staticmethod
    def _extract_features(text: str, brands_set: Set[str] = None) -> Dict[str, Any]:
        """
        Извлекает ключевые слова, бренд и количество из строки.
        Бренд определяется как самый длинный ключ, который является префиксом названия.
        """
        if not text:
            return {'keywords': set(), 'brand': None, 'count': None}

        text = str(text).strip()

        # 1. Извлекаем количество в упаковке (число перед "ШТ", "капс", "таб" и т.п.)
        count = None
        count_pattern = re.compile(
            r'(\d+)\s*(?:штук|шт|капс|капсул|капсулы|таб|таблеток|таблетки|vcaps|tabs|caps|softgels|sgels|loz|tablets|capsules)',
            re.IGNORECASE
        )
        count_match = count_pattern.search(text)
        if count_match:
            count = int(count_match.group(1))
            text = count_pattern.sub('', text)

        # 2. Определяем, есть ли английское название в скобках
        # Ищем первую пару круглых скобок, содержащую латинские буквы
        english_part = None
        parens = re.findall(r'\(([^)]*)\)', text)
        for p in parens:
            if re.search(r'[a-zA-Z]', p):
                english_part = p
                break

        if english_part:
            base_text = english_part
        else:
            base_text = text

        # Удаляем лишние пробелы
        base_text = re.sub(r'\s+', ' ', base_text).strip()

        # 3. Извлекаем бренд (ищем префикс среди ключей)
        brand = None
        if brands_set:
            base_lower = base_text.lower()
            # Сортируем ключи по убыванию длины (чтобы сначала проверить более длинные фразы)
            sorted_keys = sorted(brands_set, key=len, reverse=True)
            for key in sorted_keys:
                # Проверяем, что base_text начинается с ключа (с учётом пробела)
                if base_lower.startswith(key + ' ') or base_lower == key:
                    brand = key
                    # Удаляем ключ из base_text (обрезаем префикс)
                    if base_lower.startswith(key + ' '):
                        base_text = base_text[len(key) + 1:].strip()
                    else:
                        base_text = ""
                    break

        # 4. Извлекаем ключевые слова из оставшегося base_text
        word_pattern = re.compile(r'[a-zа-я0-9]+(?:[-’][a-zа-я0-9]+)*', re.IGNORECASE)
        keywords = set()
        for word in word_pattern.findall(base_text.lower()):
            if len(word) < 2:
                continue
            stop_words = {'бад', 'к', 'пище', 'dietary', 'supplement', 'with', 'plus', 'and', 'for', 'the'}
            if word in stop_words:
                continue
            if word.isdigit():
                continue
            keywords.add(word)

        # Добавляем количество и бренд в ключевые слова (для этапов сравнения)
        if count is not None:
            keywords.add(str(count))
        if brand:
            keywords.add(brand.lower())

        return {'keywords': keywords, 'brand': brand, 'count': count}

class MappingRecord:
        def __init__(self, article: str, shk: str, brand: str, supply_name: str, candidate_name: str):
            self.article = article
            self.shk = shk
            self.brand = brand
            self.supply_name = supply_name
            self.candidate_name = candidate_name

        def to_dict(self):
            return {
                "article": self.article,
                "shk": self.shk,
                "brand": self.brand,
                "supply_name": self.supply_name,
                "candidate_name": self.candidate_name
            }

        @classmethod
        def from_dict(cls, data):
            return cls(
                article=data["article"],
                shk=data["shk"],
                brand=data.get("brand", ""),
                supply_name=data.get("supply_name", ""),
                candidate_name=data.get("candidate_name", "")
            )

class Stage1:
    """Жёсткая сверка (этап 1)."""

    def __init__(self, log_callback=None):
        self.log = log_callback or print

    def run(self, items: List[SupplyItem], candidates: List[Candidate], parent_widget=None) -> Tuple[
        List[SupplyItem], List[SupplyItem], List[Candidate]]:
        self.log("=== ЭТАП 1: ЖЁСТКАЯ СВЕРКА ===")

        # Строим индексы
        keyword_index = {}
        count_index = {}
        for idx, cand in enumerate(candidates):
            for word in cand.keywords:
                keyword_index.setdefault(word, []).append(idx)
            if cand.count is not None:
                count_index.setdefault(cand.count, []).append(idx)

        found_pairs = []  # временный список всех жёстких совпадений
        remaining = []
        remaining_candidates = candidates.copy()

        for item in items:
            if not item.keywords:
                self.log(f"  Товар '{item.name}' не имеет ключевых слов — пропускаем")
                remaining.append(item)
                continue

            # Пересечение индексов для всех ключевых слов
            candidate_indices = None
            for word in item.keywords:
                indices = keyword_index.get(word, [])
                if not indices:
                    candidate_indices = []
                    break
                if candidate_indices is None:
                    candidate_indices = set(indices)
                else:
                    candidate_indices.intersection_update(indices)

            if not candidate_indices:
                remaining.append(item)
                continue

            # Фильтр по количеству
            if item.count is not None:
                count_indices = count_index.get(item.count, [])
                candidate_indices = [idx for idx in candidate_indices if idx in count_indices]
                if not candidate_indices:
                    remaining.append(item)
                    continue

            # Исключаем уже использованных кандидатов (на случай, если они были задействованы ранее)
            candidate_indices = [idx for idx in candidate_indices if not remaining_candidates[idx].used]

            if len(candidate_indices) == 1:
                idx = candidate_indices[0]
                cand = remaining_candidates[idx]
                # Запоминаем пару для дальнейшего решения (пока не помечаем used)
                found_pairs.append((item, cand))
            else:
                remaining.append(item)

        # Если есть совпадения и передан parent_widget — показываем диалог
        if found_pairs and parent_widget:
            from ui.windows.compare_window import Stage1ReviewDialog
            dialog = Stage1ReviewDialog(parent_widget, found_pairs)
            dialog.exec()
            keep_flags = dialog.get_keep_flags()

            # Применяем выбор пользователя
            found = []
            for i, (item, candidate) in enumerate(found_pairs):
                if keep_flags[i]:
                    candidate.used = True
                    item.found = True
                    item.matched_candidate = candidate
                    item.stage = 1
                    found.append(item)
                    self.log(f"  Жёсткое совпадение подтверждено: '{item.name}' ↔ '{candidate.name}'")
                else:
                    # Исключаем — кандидат остаётся свободным, товар переходит к следующим этапам
                    self.log(f"  Жёсткое совпадение исключено: '{item.name}' ↔ '{candidate.name}'")
                    remaining.append(item)
        else:
            # Если диалог не нужен (нет parent_widget), просто принимаем все совпадения
            found = []
            for item, candidate in found_pairs:
                candidate.used = True
                item.found = True
                item.matched_candidate = candidate
                item.stage = 1
                found.append(item)
                self.log(f"  Жёсткое совпадение: '{item.name}' ↔ '{candidate.name}'")

        self.log(f"Найдено жёстких совпадений: {len(found)}")
        self.log(f"Осталось товаров: {len(remaining)}")
        return found, remaining, remaining_candidates

class Stage2:
    """Мягкая сверка с подтверждением (этап 2)."""

    def __init__(self, parent_widget, log_callback=None):
        self.parent = parent_widget
        self.log = log_callback or print

    def run(self, items: List[SupplyItem], candidates: List[Candidate]) -> Tuple[List[SupplyItem], List[SupplyItem], List[Candidate]]:
        self.log("=== ЭТАП 2: МЯГКАЯ СВЕРКА (ЖАККАР >= 0.7) ===")

        found = []
        remaining = []
        remaining_candidates = candidates.copy()
        total = len(items)
        processed = 0

        for item in items:
            processed += 1
            if not item.keywords:
                remaining.append(item)
                continue

            candidate_indices = []
            for idx, cand in enumerate(remaining_candidates):
                if cand.used:
                    continue
                if item.count is not None and cand.count != item.count:
                    continue
                if not cand.keywords:
                    continue
                inter = len(item.keywords & cand.keywords)
                union = len(item.keywords | cand.keywords)
                if union == 0:
                    continue
                jaccard = inter / union
                if jaccard >= 0.7:
                    candidate_indices.append((idx, jaccard))

            if not candidate_indices:
                remaining.append(item)
                continue

            candidate_indices.sort(key=lambda x: x[1], reverse=True)
            best_idx, best_score = candidate_indices[0]

            if len(candidate_indices) > 1 and candidate_indices[1][1] >= 0.7:
                remaining.append(item)
                continue

            cand = remaining_candidates[best_idx]
            from ui.windows.compare_window import ConfirmMatchDialog
            dialog = ConfirmMatchDialog(
                self.parent,
                {'name': item.name, 'count': item.count},
                {'name': cand.name, 'count': cand.count},
                best_score,
                total - processed + 1
            )
            dialog.exec()
            result = dialog.get_result()

            if result == "confirmed":
                cand.used = True
                item.found = True
                item.matched_candidate = cand
                item.stage = 2
                found.append(item)
                self.log(f"  Мягкое совпадение подтверждено: '{item.name}' ↔ '{cand.name}' (Жаккар: {best_score:.2f})")
            else:
                remaining.append(item)

        self.log(f"Найдено мягких совпадений: {len(found)}")
        self.log(f"Осталось товаров для этапа 3: {len(remaining)}")
        return found, remaining, remaining_candidates

class Stage3:
    def __init__(self, parent_widget=None, log_callback=None):
        self.parent = parent_widget
        self.log = log_callback or print

    def run(self, items: List[SupplyItem], candidates: List[Candidate]) -> List[SupplyItem]:
        self.log("=== ЭТАП 3: РУЧНОЙ ВЫБОР ===")

        remaining_candidates = [c for c in candidates if not c.used]
        all_items = []  # финальный результат (все товары, найденные или нет)

        # Основной список для обработки
        current_items = items.copy()
        deferred_items = []  # товары, отложенные пользователем

        # Пока есть товары для обработки (текущие или отложенные)
        while current_items or deferred_items:
            if not current_items:
                # Если текущие закончились, но есть отложенные, переключаемся на них
                current_items = deferred_items
                deferred_items = []
                self.log("Переход к отложенным товарам...")
                continue

            item = current_items.pop(0)  # берём первый товар из очереди

            # Формируем список кандидатов для диалога
            candidates_for_dialog = [
                {'name': c.name, 'count': c.count}
                for c in remaining_candidates
            ]

            if not candidates_for_dialog:
                self.log(f"Товар '{item.name}': нет доступных кандидатов, пропускаем.")
                item.found = False
                item.stage = 0
                all_items.append(item)
                continue

            from ui.windows.compare_window import ManualMatchDialog
            dialog = ManualMatchDialog(
                self.parent,
                {'name': item.name, 'count': item.count},
                candidates_for_dialog,
                len(current_items) + len(deferred_items) + 1  # общее количество оставшихся
            )
            dialog.exec()
            selected_candidate, skip_all = dialog.get_result()

            if selected_candidate:
                matched_cand = None
                for c in remaining_candidates:
                    if c.name == selected_candidate['name'] and c.count == selected_candidate.get('count'):
                        matched_cand = c
                        break
                if matched_cand:
                    remaining_candidates.remove(matched_cand)
                    matched_cand.used = True
                    item.found = True
                    item.matched_candidate = matched_cand
                    item.stage = 3
                    self.log(f"  Ручное сопоставление: '{item.name}' ↔ '{matched_cand.name}'")
                else:
                    item.found = False
                    item.stage = 0
                all_items.append(item)
            else:
                if skip_all:
                    # Кнопка "Отложить" (переименована)
                    self.log(f"  Товар отложен: '{item.name}'")
                    deferred_items.append(item)  # добавляем в конец отложенных
                else:
                    # Кнопка "Пропустить" (без "все")
                    self.log(f"  Товар пропущен: '{item.name}'")
                    item.found = False
                    item.stage = 0
                    all_items.append(item)

        # После завершения цикла
        unused = [c for c in remaining_candidates if not c.used]
        if unused:
            self.log(f"Неиспользованных кандидатов (лишние в поставках): {len(unused)}")

        self.log("Этап 3 завершён.")
        return all_items

class ReportGenerator:
    """Формирование отчётов."""

    def __init__(self, log_callback=None):
        self.log = log_callback or print

    def generate(self, items: List[SupplyItem], output_dir: Path, candidates: List[Candidate] = None) -> None:
        self.log("=== ФОРМИРОВАНИЕ ОТЧЁТА ===")

        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Excel-отчёт
        report_path = output_dir / f"Отчёт_сравнения_{date_str}.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Сравнение"

        headers = ["№", "Наименование листа", "Кол-во лист",
                   "Наименование поставки", "Кол-во поставки",
                   "Серийный номер", "Этап", "Разница"]
        for col, h in enumerate(headers, start=1):
            ws.cell(row=1, column=col, value=h)

        row_num = 2
        not_found = []
        for item in items:
            if item.found and item.matched_candidate:
                cand = item.matched_candidate
                ws.cell(row=row_num, column=1, value=item.row_num)
                ws.cell(row=row_num, column=2, value=item.name)
                ws.cell(row=row_num, column=3, value=item.count)
                ws.cell(row=row_num, column=4, value=cand.name)
                ws.cell(row=row_num, column=5, value=cand.count)
                ws.cell(row=row_num, column=6, value=cand.serial)
                ws.cell(row=row_num, column=7, value=f"Этап {item.stage}")
                diff = (item.count - cand.count) if (item.count is not None and cand.count is not None) else "?"
                ws.cell(row=row_num, column=8, value=diff)
            else:
                not_found.append(item)
                ws.cell(row=row_num, column=1, value=item.row_num)
                ws.cell(row=row_num, column=2, value=item.name)
                ws.cell(row=row_num, column=3, value=item.count)
                ws.cell(row=row_num, column=7, value="Не найдено")
            row_num += 1

        wb.save(report_path)
        wb.close()
        self.log(f"Отчёт сохранён: {report_path.name}")

        # 2. Список не найденных
        if not_found:
            not_found_path = output_dir / f"Не_найдено_{date_str}.txt"
            with open(not_found_path, "w", encoding="utf-8") as f:
                f.write("Товары из листа поставки, не найденные в поставках:\n")
                f.write("=" * 60 + "\n")
                for item in not_found:
                    f.write(f"{item.name} (кол-во: {item.count})\n")
            self.log(f"Список не найденных сохранён: {not_found_path.name}")

        # 3. Список лишних в поставках (если передан список кандидатов)
        if candidates is not None:
            unused_candidates = [c for c in candidates if not c.used]
            if unused_candidates:
                unused_path = output_dir / f"Лишние_в_поставках_{date_str}.txt"
                with open(unused_path, "w", encoding="utf-8") as f:
                    f.write("Товары из поставок, которых нет в листе (лишние):\n")
                    f.write("=" * 60 + "\n")
                    for c in unused_candidates:
                        f.write(f"{c.name} (кол-во: {c.count})\n")
                self.log(f"Список лишних в поставках сохранён: {unused_path.name}")

class CompareService:
    def __init__(self, log_callback=None, brands_set: Set[str] = None):
        self.log_callback = log_callback or print
        self.brands_set = brands_set or set()
        self.brands_from_config = []
        self.data_loader = DataLoader(brands_set=self.brands_set, log_callback=self.log_callback)
        self.stage1 = Stage1(log_callback=self.log_callback)
        self.report_generator = ReportGenerator(log_callback=self.log_callback)
        self.copied_supply_path: Optional[Path] = None
        self.consolidated_supply_path: Optional[Path] = None
        self.supply_items: List[SupplyItem] = []
        self.candidates: List[Candidate] = []
        self.found_stage1: List[SupplyItem] = []
        self.found_stage2: List[SupplyItem] = []
        self.final_items: List[SupplyItem] = []

    def set_brands_from_config(self, brands):
        self.brands_from_config = brands

    def log(self, msg: str) -> None:
        self.log_callback(msg)

    def _get_mappings_path(self) -> Path:
        """Возвращает путь к файлу mappings.json в папке приложения."""
        # Предполагаем, что compare_service.py находится в корневой папке проекта
        return Path(__file__).parent.parent / "data" / "mappings.json"

    def _normalize_brand_names(self, mappings, brands_from_config):
        if not self.brands_from_config:
            return mappings
        brand_map = {b.name: b for b in self.brands_from_config}
        normalized = {}
        for brand_name, articles in mappings.items():
            canonical = None
            lower_name = brand_name.lower()
            for b in brand_map.values():
                if b.name.lower() == lower_name:
                    canonical = b.name
                    break
            if canonical is None:
                for b in brand_map.values():
                    if any(brand_name.lower() in key.lower() for key in b.keys):
                        canonical = b.name
                        break
            if canonical is None:
                canonical = brand_name
            if canonical in normalized:
                normalized[canonical].update(articles)
            else:
                normalized[canonical] = articles.copy()
        return normalized

    def _convert_legacy_mappings(self, data):
        """
        Конвертирует старый формат маппингов (список) в новый (словарь брендов).
        """
        if isinstance(data, list):
            converted = {}
            for entry in data:
                brand = entry.get("brand", "")
                article = entry.get("article", "")
                shk = entry.get("shk", "")
                supply_name = entry.get("supply_name", "")
                candidate_name = entry.get("candidate_name", "")
                if brand not in converted:
                    converted[brand] = {}
                converted[brand][article] = {
                    "shk": shk,
                    "supply_name": supply_name,
                    "candidate_name": candidate_name
                }
            return converted
        return data


    def load_mappings(self) -> Dict[str, Dict[str, Dict]]:
        mappings_path = self._get_mappings_path()
        if not mappings_path.exists():
            return {}
        try:
            with open(mappings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Проверяем формат и конвертируем при необходимости
                for brand, articles in data.items():
                    if not isinstance(articles, dict):
                        data = self._convert_legacy_mappings(data)
                        break
                # Нормализуем имена брендов, если есть brands_from_config
                if hasattr(self, 'brands_from_config') and self.brands_from_config:
                    if self.brands_from_config:
                        data = self._normalize_brand_names(data, self.brands_from_config)
                return data
            else:
                data = self._convert_legacy_mappings(data)
                if self.brands_from_config:
                    data = self._normalize_brand_names(data, self.brands_from_config)
                return data
        except (json.JSONDecodeError, IOError):
            return {}

    def _collect_mappings(self) -> dict:
        """
        Собирает текущие сопоставления из найденных товаров.
        Возвращает словарь вида {brand: {article: {"shk": ..., "supply_name": ..., "candidate_name": ...}}}
        """
        mappings = {}
        all_items = []
        all_items.extend(self.found_stage1)
        all_items.extend(self.found_stage2)
        all_items.extend(self.final_items)

        for item in all_items:
            if item.found and item.matched_candidate and item.article:
                brand = item.brand or "Без бренда"
                article = item.article
                shk = item.matched_candidate.shk or ""
                supply_name = item.matched_candidate.name or ""
                candidate_name = item.name or ""

                if brand not in mappings:
                    mappings[brand] = {}
                mappings[brand][article] = {
                    "shk": shk,
                    "supply_name": supply_name,
                    "candidate_name": candidate_name
                }
        return mappings

    def save_mappings(self, mappings=None) -> None:
        """
        Сохраняет сопоставления в файл. Если mappings не переданы, собирает из текущих данных.
        Файл полностью перезаписывается переданным словарём.
        """
        if mappings is None:
            mappings = self._collect_mappings()
            if not mappings:
                self.log("Нет сопоставлений для сохранения")
                return

        # Нормализуем имена брендов, если есть brands_from_config
        if self.brands_from_config:
            mappings = self._normalize_brand_names(mappings, self.brands_from_config)

        mappings_path = self._get_mappings_path()
        try:
            with open(mappings_path, "w", encoding="utf-8") as f:
                json.dump(mappings, f, ensure_ascii=False, indent=4)
            self.log(f"Сохранено брендов: {len(mappings)}")
        except IOError as e:
            self.log(f"Ошибка сохранения сопоставлений: {e}")

    def _apply_mappings(self, items: List[SupplyItem], candidates: List[Candidate]) -> Tuple[
        List[SupplyItem], List[Candidate]]:
        mappings = self.load_mappings()
        if not mappings:
            return items, candidates

        remaining_items = []
        remaining_candidates = candidates.copy()

        for item in items:
            if not item.article:
                remaining_items.append(item)
                continue

            found = False
            for brand, articles in mappings.items():
                if item.article in articles:
                    shk = articles[item.article]["shk"]
                    matched_cand = None
                    for cand in remaining_candidates:
                        if cand.shk == shk and not cand.used:
                            matched_cand = cand
                            break
                    if matched_cand:
                        matched_cand.used = True
                        item.found = True
                        item.matched_candidate = matched_cand
                        item.stage = 1
                        self.log(f"  Применено сохранённое сопоставление: {item.article} -> {shk}")
                        found = True
                        break
                    else:
                        self.log(f"  Не найден кандидат для сохранённого сопоставления: {item.article} -> {shk}")
                        found = True  # мы обработали этот артикул, но не нашли кандидата
                        break
            if not found:
                remaining_items.append(item)

        remaining_candidates = [c for c in remaining_candidates if not c.used]
        return remaining_items, remaining_candidates

    def copy_supply_sheet(self, supply_file_path: str, output_dir: str) -> Path:
        self.log("=== КОПИРОВАНИЕ ЛИСТА ПОСТАВКИ ===")
        supply_path = Path(supply_file_path)
        if not supply_path.exists():
            raise FileNotFoundError(f"Файл листа поставки не найден: {supply_file_path}")

        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        copy_name = f"Лист_поставки_копия_{date_str}.xlsx"
        copy_path = output_dir_path / copy_name

        self.log(f"Исходный файл: {supply_path.name}")
        self.log(f"Копия: {copy_path.name}")

        # Открываем файл НЕ в read-only режиме
        wb = ExcelHelper.open_data_file(supply_path, read_only=False, data_only=True)
        ws = wb.active

        # Проверяем, что лист не пустой
        if ws.max_row is not None and ws.max_row > 0 and ws.max_column is not None and ws.max_column > 0:
            max_col = ws.max_column
            ws.cell(row=1, column=max_col + 1, value="Итоговое количество")
            ws.cell(row=1, column=max_col + 2, value="КИЗ")
            self.log("  Добавлены столбцы 'Итоговое количество' и 'КИЗ'")
        else:
            self.log(f"  max_row={ws.max_row}, max_column={ws.max_column}")
            self.log("  Лист пуст или не содержит данных — столбцы не добавлены")

        wb.save(copy_path)
        wb.close()

        self.copied_supply_path = copy_path
        return copy_path

    def build_consolidated_supply(self, supply_files: List[str], output_dir: str) -> Path:
        self.log("=== ФОРМИРОВАНИЕ СБОРНОГО ФАЙЛА ПОСТАВОК ===")
        if not supply_files:
            raise ValueError("Список файлов поставок пуст.")

        consolidated = {}
        skipped_no_gtin = 0
        total_files = len(supply_files)

        # Создаём папку для логов
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        for idx, file_path in enumerate(supply_files, start=1):
            file_path = Path(file_path)
            self.log(f"Обработка файла {idx}/{total_files}: {file_path.name}")

            # ---- Если это CSV, используем нормализатор по строкам ----
            if file_path.suffix.lower() == '.csv':
                try:
                    from utils.excel_helper import CsvNormalizer
                    normalizer = CsvNormalizer(file_path)
                    valid_rows, invalid_log = normalizer.normalize_rows(self.log)

                    # Сохраняем лог некорректных строк
                    if invalid_log:
                        log_path = output_dir_path / f"log_некорректные_строки_{file_path.stem}.txt"
                        with open(log_path, 'w', encoding='utf-8') as f:
                            f.write(f"Некорректные строки в файле {file_path.name}\n")
                            f.write("=" * 60 + "\n")
                            for line in invalid_log:
                                f.write(line + "\n")
                        self.log(f"  Некорректные строки сохранены в {log_path.name}")

                    # Обрабатываем валидные строки
                    if valid_rows:
                        self.log(f"  Найдено валидных строк: {len(valid_rows)}")
                        for row in valid_rows:
                            gtin = row['gtin']
                            kiz = row['kiz']
                            name = row['name']
                            count = int(row['count']) if row['count'].isdigit() else 1

                            if gtin not in consolidated:
                                consolidated[gtin] = {
                                    'original_name': name,
                                    'count': 0,
                                    'serial': kiz,
                                    'source_file': file_path.name,
                                    'gtin': gtin
                                }
                            consolidated[gtin]['count'] += count
                            if not consolidated[gtin]['serial'] and kiz:
                                consolidated[gtin]['serial'] = kiz
                            if not consolidated[gtin]['original_name'] and name:
                                consolidated[gtin]['original_name'] = name
                    else:
                        self.log("  Валидных строк не найдено")

                except Exception as e:
                    self.log(f"  Ошибка обработки CSV через нормализатор: {e}")
                    continue

            # ---- Если это Excel, используем стандартный подход ----
            else:
                try:
                    wb = ExcelHelper.open_data_file(file_path, read_only=True, data_only=True)
                    ws = wb.active
                except Exception as e:
                    self.log(f"  Ошибка открытия: {e} – пропускаем")
                    continue

                header_variants = {
                    'name': ["Наименование", "Name", "Product name", "Description", "Товар"],
                    'shk': ["ШК", "GTIN", "Штрихкод", "Barcode", "Код маркировки"],
                    'serial': ["Серийный номер", "Serial number", "Код", "S/N"]
                }

                header_row, columns = self.data_loader._find_header_row_and_columns(ws, header_variants)
                if header_row is None or columns is None:
                    self.log(f"  Не удалось найти заголовки в файле {file_path.name}, пропускаем")
                    wb.close()
                    continue

                col_name = columns.get('name')
                col_shk = columns.get('shk')
                col_serial = columns.get('serial')

                if col_name is None or col_shk is None:
                    self.log(f"  В файле {file_path.name} не найдены столбцы 'Наименование' или 'ШК', пропускаем")
                    wb.close()
                    continue

                self.log(f"  Заголовки: наименование={col_name}, ШК={col_shk}, серийный={col_serial}")

                row_count = 0
                for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                    shk = row[col_shk] if len(row) > col_shk else None
                    if not shk:
                        skipped_no_gtin += 1
                        continue
                    shk_key = str(shk).strip()
                    if not shk_key:
                        skipped_no_gtin += 1
                        continue

                    name = str(row[col_name]).strip() if row[col_name] else ""
                    serial = row[col_serial] if col_serial is not None and len(row) > col_serial else None

                    if shk_key in consolidated:
                        if consolidated[shk_key]['count'] is None:
                            consolidated[shk_key]['count'] = 0
                        consolidated[shk_key]['count'] += 1
                        if consolidated[shk_key]['serial'] is None and serial:
                            consolidated[shk_key]['serial'] = str(serial).strip()
                    else:
                        consolidated[shk_key] = {
                            'original_name': name,
                            'count': 1,
                            'serial': str(serial).strip() if serial else None,
                            'source_file': file_path.name,
                            'gtin': shk_key
                        }
                    row_count += 1

                wb.close()
                self.log(f"  Прочитано строк: {row_count}")

        self.log(f"Всего уникальных GTIN/ШК: {len(consolidated)}")

        if not consolidated:
            raise ValueError("Не найдено ни одной записи с GTIN/ШК в файлах поставок.")

        # Сохраняем сборный файл
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        consolidated_name = f"Сборный_поставок_{date_str}.xlsx"
        consolidated_path = output_dir_path / consolidated_name

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Поставки"
        headers = ["ШК", "Наименование", "Количество", "Серийный номер", "Файл-источник"]
        for col, h in enumerate(headers, start=1):
            ws.cell(row=1, column=col, value=h)

        row_num = 2
        for shk_key, data in consolidated.items():
            ws.cell(row=row_num, column=1, value=shk_key)
            ws.cell(row=row_num, column=2, value=data['original_name'])
            ws.cell(row=row_num, column=3, value=data['count'] if data['count'] is not None else 0)
            ws.cell(row=row_num, column=4,
                    value=TextUtils.clean_invalid_excel_chars(data['serial']) if data['serial'] else '')
            ws.cell(row=row_num, column=5, value=data['source_file'])
            row_num += 1

        wb.save(consolidated_path)
        wb.close()
        self.log(f"Сборный файл сохранён: {consolidated_path.name}")

        self.consolidated_supply_path = consolidated_path
        return consolidated_path

    def run_stage1(self, parent_widget=None) -> None:
        if not self.supply_items or not self.candidates:
            raise RuntimeError("Данные не загружены. Выполните подготовку и загрузку.")
        # Применяем сохранённые сопоставления
        remaining_items, remaining_candidates = self._apply_mappings(self.supply_items, self.candidates)
        # Запускаем этап 1 для оставшихся
        found, remaining, updated_candidates = self.stage1.run(
            remaining_items, remaining_candidates, parent_widget
        )
        # Собираем все найденные на этапе 1 (включая уже сопоставленные через маппинги)
        mapped_items = [item for item in self.supply_items if item not in remaining_items]
        self.found_stage1 = found + mapped_items
        self.supply_items = remaining
        self.candidates = updated_candidates

    def run_stage2(self, parent_widget) -> None:
        if not self.supply_items or not self.candidates:
            raise RuntimeError("Данные не загружены.")
        stage2 = Stage2(parent_widget, log_callback=self.log_callback)
        self.found_stage2, self.supply_items, self.candidates = stage2.run(
            self.supply_items, self.candidates
        )

    def run_stage3(self, parent_widget) -> None:
        if not self.supply_items or not self.candidates:
            raise RuntimeError("Данные не загружены.")
        stage3 = Stage3(parent_widget, log_callback=self.log_callback)
        self.final_items = stage3.run(self.supply_items, self.candidates)

    def load_data(self) -> None:
        if not self.copied_supply_path or not self.consolidated_supply_path:
            raise RuntimeError("Сначала выполните подготовку файлов.")
        self.supply_items = self.data_loader.load_supply_items(self.copied_supply_path)
        self.candidates = self.data_loader.load_candidates(self.consolidated_supply_path)

    def generate_report(self, output_dir: str) -> None:
        if not self.final_items:
            raise RuntimeError("Нет финальных данных. Выполните этап 3.")

        # Объединяем все найденные товары
        all_items = []
        all_items.extend(self.found_stage1)
        all_items.extend(self.found_stage2)
        all_items.extend(self.final_items)

        # Передаём список кандидатов для поиска лишних
        self.report_generator.generate(all_items, Path(output_dir), self.candidates)

