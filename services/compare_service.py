# services/compare_service.py
import re
import json
from pathlib import Path
from datetime import date
from typing import List, Tuple, Optional, Set, Dict, Any

import openpyxl

from models.models import SupplyItem, Candidate
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.logger import ILogger
from utils.path_utils import AppPaths


class DataLoader:
    """Загрузка данных из подготовленных Excel-файлов."""

    def __init__(self, brands_set: Set[str] = None, logger: ILogger = None):
        self.brands_set = brands_set or set()
        self.logger = logger

    @staticmethod
    def _find_header_row_and_columns(sheet, header_variants: dict, max_rows=15, max_cols=20) -> tuple:
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
            header_row = header_row[:max_cols]

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

            if 'name' in found_columns and ('shk' in found_columns or 'count' in found_columns):
                return row_idx, found_columns

            if score > best_score:
                best_score = score
                best_row = row_idx
                best_columns = found_columns

        if best_row is None or best_score < 2 or 'name' not in best_columns:
            return None, None
        return best_row, best_columns

    def load_supply_items(self, file_path: Path) -> List[SupplyItem]:
        if self.logger:
            self.logger.info(f"Загрузка товаров из листа поставки: {file_path.name}")
        items = []
        try:
            wb = ExcelHelper.open_data_file(file_path, read_only=True, data_only=True)
            ws = wb.active

            header_variants = {
                'article': ["Артикул", "SKU", "Article", "Код", "Product code"],
                'name': ["Наименование", "Name", "Product name", "Description", "Товар"],
                'count': ["Количество", "Quantity", "Qty", "Кол-во"],
                'row_num': ["№", "№ п/п", "№ п.п.", "Номер", "Item", "Row"]
            }

            header_row, columns = self._find_header_row_and_columns(ws, header_variants)
            if header_row is None or columns is None:
                if self.logger:
                    self.logger.error("Не удалось найти заголовки таблицы. Проверьте структуру файла.")
                wb.close()
                return []

            if self.logger:
                self.logger.debug(f"Заголовки найдены в строке {header_row}")
                self.logger.debug(
                    f"Столбцы: артикул={columns.get('article')}, наименование={columns.get('name')}, "
                    f"количество={columns.get('count')}, №={columns.get('row_num')}"
                )

            col_article = columns.get('article')
            col_name = columns.get('name')
            col_count = columns.get('count')
            col_row_num = columns.get('row_num')

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
            if self.logger:
                self.logger.error(f"Ошибка загрузки листа поставки: {e}")
            raise

        if self.logger:
            self.logger.info(f"Загружено товаров: {len(items)}")
            if items:
                self.logger.debug("Первые 5 товаров (имя, количество):")
                for i, item in enumerate(items[:5]):
                    self.logger.debug(f"  {i + 1}. {item.name} | кол-во: {item.count} | keywords: {item.keywords}")
        return items

    def load_candidates(self, file_path: Path) -> List[Candidate]:
        if self.logger:
            self.logger.info(f"Загрузка кандидатов из сборного файла: {file_path.name}")
        candidates = []
        try:
            wb = ExcelHelper.open_data_file(file_path, read_only=True, data_only=True)
            ws = wb.active

            header_variants = {
                'name': ["Наименование", "Name"],
                'count': ["Количество_строк", "Количество строк", "Count", "Quantity", "Количество"],
                'serial': ["Серийный_номер", "Serial number"],
                'source_file': ["Файл_источник", "Source file"],
                'shk': ["ШК", "GTIN", "Barcode"]
            }

            header_row, columns = self._find_header_row_and_columns(ws, header_variants)
            if header_row is None or columns is None:
                if self.logger:
                    self.logger.error("Не удалось найти заголовки в сборном файле.")
                wb.close()
                return []

            col_name = columns.get('name')
            col_count = columns.get('count')
            col_serial = columns.get('serial')
            col_source = columns.get('source_file')
            col_shk = columns.get('shk')

            if col_name is None or col_shk is None:
                if self.logger:
                    self.logger.error("В сборном файле не найдены столбцы 'Наименование' или 'ШК'.")
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
            if self.logger:
                self.logger.error(f"Ошибка загрузки сборного файла: {e}")
            raise

        if self.logger:
            self.logger.info(f"Загружено кандидатов: {len(candidates)}")
            if candidates:
                self.logger.debug("Первые 5 кандидатов с ключевыми словами:")
                for i, cand in enumerate(candidates[:5]):
                    self.logger.debug(f"  {i+1}. {cand.name} -> keywords: {cand.keywords}")
        return candidates

    def load_csv_via_normalizer(self, file_path: Path) -> List[Dict[str, str]]:
        from utils.excel_helper import CsvNormalizer
        normalizer = CsvNormalizer(file_path)
        valid_rows, invalid_log = normalizer.normalize_rows(
            lambda msg: self.logger.debug(msg) if self.logger else None
        )

        if invalid_log:
            log_path = Path(file_path).parent / f"log_некорректные_строки_{Path(file_path).stem}.txt"
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"Некорректные строки в файле {Path(file_path).name}\n")
                f.write("=" * 60 + "\n")
                for line in invalid_log:
                    f.write(line + "\n")
            if self.logger:
                self.logger.info(f"Некорректные строки сохранены в {log_path.name}")

        return valid_rows

    @staticmethod
    def _extract_features(text: str, brands_set: Set[str] = None) -> Dict[str, Any]:
        if not text:
            return {'keywords': set(), 'brand': None, 'count': None}

        text = str(text).strip()

        count = None
        count_pattern = re.compile(
            r'(\d+)\s*(?:штук|шт|капс|капсул|капсулы|таб|таблеток|таблетки|vcaps|tabs|caps|softgels|sgels|loz|tablets|capsules)',
            re.IGNORECASE
        )
        count_match = count_pattern.search(text)
        if count_match:
            count = int(count_match.group(1))
            text = count_pattern.sub('', text)

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

        base_text = re.sub(r'\s+', ' ', base_text).strip()

        brand = None
        if brands_set:
            base_lower = base_text.lower()
            sorted_keys = sorted(brands_set, key=len, reverse=True)
            for key in sorted_keys:
                if base_lower.startswith(key + ' ') or base_lower == key:
                    brand = key
                    if base_lower.startswith(key + ' '):
                        base_text = base_text[len(key) + 1:].strip()
                    else:
                        base_text = ""
                    break

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

        if count is not None:
            keywords.add(str(count))
        if brand:
            keywords.add(brand.lower())

        return {'keywords': keywords, 'brand': brand, 'count': count}


class Stage1:
    """Жёсткая сверка (этап 1)."""

    def __init__(self, logger: ILogger = None):
        self.logger = logger

    def run(self, items: List[SupplyItem], candidates: List[Candidate], parent_widget=None) -> Tuple[
        List[SupplyItem], List[SupplyItem], List[Candidate]]:
        if self.logger:
            self.logger.info("=== ЭТАП 1: ЖЁСТКАЯ СВЕРКА ===")

        keyword_index = {}
        count_index = {}
        for idx, cand in enumerate(candidates):
            for word in cand.keywords:
                keyword_index.setdefault(word, []).append(idx)
            if cand.count is not None:
                count_index.setdefault(cand.count, []).append(idx)

        found_pairs = []
        remaining = []
        remaining_candidates = candidates.copy()

        for item in items:
            if not item.keywords:
                if self.logger:
                    self.logger.debug(f"  Товар '{item.name}' не имеет ключевых слов — пропускаем")
                remaining.append(item)
                continue

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

            if item.count is not None:
                count_indices = count_index.get(item.count, [])
                candidate_indices = [idx for idx in candidate_indices if idx in count_indices]
                if not candidate_indices:
                    remaining.append(item)
                    continue

            candidate_indices = [idx for idx in candidate_indices if not remaining_candidates[idx].used]

            if len(candidate_indices) == 1:
                idx = candidate_indices[0]
                cand = remaining_candidates[idx]
                found_pairs.append((item, cand))
            else:
                remaining.append(item)

        if found_pairs and parent_widget:
            from ui.windows.compare_window import Stage1ReviewDialog
            dialog = Stage1ReviewDialog(parent_widget, found_pairs)
            dialog.exec()
            keep_flags = dialog.get_keep_flags()

            found = []
            for i, (item, candidate) in enumerate(found_pairs):
                if keep_flags[i]:
                    candidate.used = True
                    item.found = True
                    item.matched_candidate = candidate
                    item.stage = 1
                    found.append(item)
                    if self.logger:
                        self.logger.debug(f"  Жёсткое совпадение подтверждено: '{item.name}' ↔ '{candidate.name}'")
                else:
                    if self.logger:
                        self.logger.debug(f"  Жёсткое совпадение исключено: '{item.name}' ↔ '{candidate.name}'")
                    remaining.append(item)
        else:
            found = []
            for item, candidate in found_pairs:
                candidate.used = True
                item.found = True
                item.matched_candidate = candidate
                item.stage = 1
                found.append(item)
                if self.logger:
                    self.logger.debug(f"  Жёсткое совпадение: '{item.name}' ↔ '{candidate.name}'")

        if self.logger:
            self.logger.info(f"Найдено жёстких совпадений: {len(found)}")
            self.logger.info(f"Осталось товаров: {len(remaining)}")
        return found, remaining, remaining_candidates


class Stage2:
    """Мягкая сверка с подтверждением (этап 2)."""

    def __init__(self, parent_widget, logger: ILogger = None):
        self.parent = parent_widget
        self.logger = logger

    def run(self, items: List[SupplyItem], candidates: List[Candidate]) -> Tuple[List[SupplyItem], List[SupplyItem], List[Candidate]]:
        if self.logger:
            self.logger.info("=== ЭТАП 2: МЯГКАЯ СВЕРКА (ЖАККАР >= 0.7) ===")

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
                if self.logger:
                    self.logger.debug(f"  Мягкое совпадение подтверждено: '{item.name}' ↔ '{cand.name}' (Жаккар: {best_score:.2f})")
            else:
                remaining.append(item)

        if self.logger:
            self.logger.info(f"Найдено мягких совпадений: {len(found)}")
            self.logger.info(f"Осталось товаров для этапа 3: {len(remaining)}")
        return found, remaining, remaining_candidates


class Stage3:
    def __init__(self, parent_widget=None, logger: ILogger = None):
        self.parent = parent_widget
        self.logger = logger

    def run(self, items: List[SupplyItem], candidates: List[Candidate]) -> List[SupplyItem]:
        if self.logger:
            self.logger.info("=== ЭТАП 3: РУЧНОЙ ВЫБОР ===")

        remaining_candidates = [c for c in candidates if not c.used]
        all_items = []
        current_items = items.copy()
        deferred_items = []

        while current_items or deferred_items:
            if not current_items:
                current_items = deferred_items
                deferred_items = []
                if self.logger:
                    self.logger.info("Переход к отложенным товарам...")
                continue

            item = current_items.pop(0)

            candidates_for_dialog = [
                {'name': c.name, 'count': c.count}
                for c in remaining_candidates
            ]

            if not candidates_for_dialog:
                if self.logger:
                    self.logger.debug(f"Товар '{item.name}': нет доступных кандидатов, пропускаем.")
                item.found = False
                item.stage = 0
                all_items.append(item)
                continue

            from ui.windows.compare_window import ManualMatchDialog
            dialog = ManualMatchDialog(
                self.parent,
                {'name': item.name, 'count': item.count},
                candidates_for_dialog,
                len(current_items) + len(deferred_items) + 1
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
                    if self.logger:
                        self.logger.debug(f"  Ручное сопоставление: '{item.name}' ↔ '{matched_cand.name}'")
                else:
                    item.found = False
                    item.stage = 0
                all_items.append(item)
            else:
                if skip_all:
                    if self.logger:
                        self.logger.debug(f"  Товар отложен: '{item.name}'")
                    deferred_items.append(item)
                else:
                    if self.logger:
                        self.logger.debug(f"  Товар пропущен: '{item.name}'")
                    item.found = False
                    item.stage = 0
                    all_items.append(item)

        unused = [c for c in remaining_candidates if not c.used]
        if unused and self.logger:
            self.logger.info(f"Неиспользованных кандидатов (лишние в поставках): {len(unused)}")

        if self.logger:
            self.logger.info("Этап 3 завершён.")
        return all_items


class ReportGenerator:
    """Формирование отчётов."""

    def __init__(self, logger: ILogger = None):
        self.logger = logger

    def generate(self, items: List[SupplyItem], output_dir: Path, candidates: List[Candidate] = None) -> None:
        if self.logger:
            self.logger.info("=== ФОРМИРОВАНИЕ ОТЧЁТА ===")

        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

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
        if self.logger:
            self.logger.info(f"Отчёт сохранён: {report_path.name}")

        if not_found:
            not_found_path = output_dir / f"Не_найдено_{date_str}.txt"
            with open(not_found_path, "w", encoding="utf-8") as f:
                f.write("Товары из листа поставки, не найденные в поставках:\n")
                f.write("=" * 60 + "\n")
                for item in not_found:
                    f.write(f"{item.name} (кол-во: {item.count})\n")
            if self.logger:
                self.logger.info(f"Список не найденных сохранён: {not_found_path.name}")

        if candidates is not None:
            unused_candidates = [c for c in candidates if not c.used]
            if unused_candidates:
                unused_path = output_dir / f"Лишние_в_поставках_{date_str}.txt"
                with open(unused_path, "w", encoding="utf-8") as f:
                    f.write("Товары из поставок, которых нет в листе (лишние):\n")
                    f.write("=" * 60 + "\n")
                    for c in unused_candidates:
                        f.write(f"{c.name} (кол-во: {c.count})\n")
                if self.logger:
                    self.logger.info(f"Список лишних в поставках сохранён: {unused_path.name}")


class CompareService:
    """Главный сервис сравнения поставок."""

    def __init__(self, logger: ILogger = None, brands_set: Set[str] = None, app_paths: AppPaths = None):
        self.logger = logger
        self.brands_set = brands_set or set()
        self.brands_from_config = []
        self.app_paths = app_paths or AppPaths()

        self.data_loader = DataLoader(brands_set=self.brands_set, logger=self.logger)
        self.stage1 = Stage1(logger=self.logger)
        self.report_generator = ReportGenerator(logger=self.logger)

        self.copied_supply_path: Optional[Path] = None
        self.consolidated_supply_path: Optional[Path] = None
        self.supply_items: List[SupplyItem] = []
        self.candidates: List[Candidate] = []
        self.found_stage1: List[SupplyItem] = []
        self.found_stage2: List[SupplyItem] = []
        self.final_items: List[SupplyItem] = []

    def set_brands_from_config(self, brands):
        self.brands_from_config = brands

    def _get_mappings_path(self) -> Path:
        return self.app_paths.get_data_path() / "mappings.json"

    def _convert_legacy_mappings(self, data):
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

    def load_mappings(self) -> Dict[str, Dict[str, Dict]]:
        mappings_path = self._get_mappings_path()
        if not mappings_path.exists():
            return {}
        try:
            with open(mappings_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                data = self._convert_legacy_mappings(data)
            elif isinstance(data, dict):
                for brand, articles in data.items():
                    if not isinstance(articles, dict):
                        data = self._convert_legacy_mappings(data)
                        break
            else:
                return {}

            if self.brands_from_config:
                data = self._normalize_brand_names(data, self.brands_from_config)
            return data
        except (json.JSONDecodeError, IOError) as e:
            if self.logger:
                self.logger.error(f"Ошибка загрузки сопоставлений: {e}")
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
        """Сохраняет сопоставления в файл. Если mappings не переданы, собирает из текущих данных.
        Если файл уже существует, новые сопоставления добавляются к существующим.
        """
        # 1. Загружаем существующие маппинги из файла
        existing = self.load_mappings()

        # 2. Определяем новые маппинги
        if mappings is None:
            new_mappings = self._collect_mappings()
        else:
            new_mappings = mappings

        # 3. Если новых нет, выходим (сохраняем как есть, но можно ничего не делать)
        if not new_mappings:
            if existing:
                self.logger.info("Нет новых сопоставлений для добавления")
            else:
                self.logger.info("Нет сопоставлений для сохранения")
            return

        # 4. Объединяем: добавляем/обновляем статьи для каждого бренда
        for brand, articles in new_mappings.items():
            if brand in existing:
                existing[brand].update(articles)  # обновляем существующие статьи
            else:
                existing[brand] = articles  # добавляем новый бренд

        # 5. Нормализуем имена брендов (если есть конфиг)
        if self.brands_from_config:
            existing = self._normalize_brand_names(existing, self.brands_from_config)

        # 6. Сохраняем объединённый словарь
        mappings_path = self._get_mappings_path()
        try:
            with open(mappings_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=4)
            self.logger.info(f"Сохранено брендов: {len(existing)} (добавлено из текущей сессии)")
        except IOError as e:
            self.logger.error(f"Ошибка сохранения сопоставлений: {e}")

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
                        if self.logger:
                            self.logger.debug(f"  Применено сохранённое сопоставление: {item.article} -> {shk}")
                        found = True
                        break
                    else:
                        if self.logger:
                            self.logger.debug(f"  Не найден кандидат для сохранённого сопоставления: {item.article} -> {shk}")
                        found = True
                        break
            if not found:
                remaining_items.append(item)

        remaining_candidates = [c for c in remaining_candidates if not c.used]
        return remaining_items, remaining_candidates

    def copy_supply_sheet(self, supply_file_path: str, output_dir: str) -> Path:
        if self.logger:
            self.logger.info("=== КОПИРОВАНИЕ ЛИСТА ПОСТАВКИ ===")
        supply_path = Path(supply_file_path)
        if not supply_path.exists():
            raise FileNotFoundError(f"Файл листа поставки не найден: {supply_file_path}")

        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        copy_name = f"Лист_поставки_копия_{date_str}.xlsx"
        copy_path = output_dir_path / copy_name

        if self.logger:
            self.logger.info(f"Исходный файл: {supply_path.name}")
            self.logger.info(f"Копия: {copy_path.name}")

        wb = ExcelHelper.open_data_file(supply_path, read_only=False, data_only=True)
        ws = wb.active

        if ws.max_row is not None and ws.max_row > 0 and ws.max_column is not None and ws.max_column > 0:
            max_col = ws.max_column
            ws.cell(row=1, column=max_col + 1, value="Итоговое количество")
            ws.cell(row=1, column=max_col + 2, value="КИЗ")
            if self.logger:
                self.logger.info("  Добавлены столбцы 'Итоговое количество' и 'КИЗ'")
        else:
            if self.logger:
                self.logger.info("  Лист пуст или не содержит данных — столбцы не добавлены")

        wb.save(copy_path)
        wb.close()

        self.copied_supply_path = copy_path
        return copy_path

    def build_consolidated_supply(self, supply_files: List[str], output_dir: str) -> Path:
        if self.logger:
            self.logger.info("=== ФОРМИРОВАНИЕ СБОРНОГО ФАЙЛА ПОСТАВОК ===")
        if not supply_files:
            raise ValueError("Список файлов поставок пуст.")

        consolidated = {}
        total_files = len(supply_files)
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        for idx, file_path in enumerate(supply_files, start=1):
            file_path = Path(file_path)
            if self.logger:
                self.logger.info(f"Обработка файла {idx}/{total_files}: {file_path.name}")

            if file_path.suffix.lower() == '.csv':
                try:
                    from utils.excel_helper import CsvNormalizer
                    normalizer = CsvNormalizer(file_path)
                    valid_rows, invalid_log = normalizer.normalize_rows(
                        lambda msg: self.logger.debug(msg) if self.logger else None
                    )

                    if invalid_log:
                        log_path = output_dir_path / f"log_некорректные_строки_{file_path.stem}.txt"
                        with open(log_path, 'w', encoding='utf-8') as f:
                            f.write(f"Некорректные строки в файле {file_path.name}\n")
                            f.write("=" * 60 + "\n")
                            for line in invalid_log:
                                f.write(line + "\n")
                        if self.logger:
                            self.logger.info(f"  Некорректные строки сохранены в {log_path.name}")

                    if valid_rows:
                        if self.logger:
                            self.logger.debug(f"  Найдено валидных строк: {len(valid_rows)}")
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
                        if self.logger:
                            self.logger.debug("  Валидных строк не найдено")
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"  Ошибка обработки CSV через нормализатор: {e}")
                    continue

            else:
                try:
                    wb = ExcelHelper.open_data_file(file_path, read_only=True, data_only=True)
                    ws = wb.active
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"  Ошибка открытия: {e} – пропускаем")
                    continue

                header_variants = {
                    'name': ["Наименование", "Name", "Product name", "Description", "Товар"],
                    'shk': ["ШК", "GTIN", "Штрихкод", "Barcode", "Код маркировки"],
                    'serial': ["Серийный номер", "Serial number", "Код", "S/N"]
                }

                header_row, columns = self.data_loader._find_header_row_and_columns(ws, header_variants)
                if header_row is None or columns is None:
                    if self.logger:
                        self.logger.debug(f"  Не удалось найти заголовки в файле {file_path.name}, пропускаем")
                    wb.close()
                    continue

                col_name = columns.get('name')
                col_shk = columns.get('shk')
                col_serial = columns.get('serial')

                if col_name is None or col_shk is None:
                    if self.logger:
                        self.logger.debug(f"  В файле {file_path.name} не найдены столбцы 'Наименование' или 'ШК', пропускаем")
                    wb.close()
                    continue

                if self.logger:
                    self.logger.debug(f"  Заголовки: наименование={col_name}, ШК={col_shk}, серийный={col_serial}")

                row_count = 0
                for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                    shk = row[col_shk] if len(row) > col_shk else None
                    if not shk:
                        continue
                    shk_key = str(shk).strip()
                    if not shk_key:
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
                if self.logger:
                    self.logger.debug(f"  Прочитано строк: {row_count}")

        if self.logger:
            self.logger.info(f"Всего уникальных GTIN/ШК: {len(consolidated)}")

        if not consolidated:
            raise ValueError("Не найдено ни одной записи с GTIN/ШК в файлах поставок.")

        consolidated_name = f"Сборный_поставок_{date.today().strftime('%d_%m_%Y')}.xlsx"
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
        if self.logger:
            self.logger.info(f"Сборный файл сохранён: {consolidated_path.name}")

        self.consolidated_supply_path = consolidated_path
        return consolidated_path

    def load_data(self) -> None:
        if not self.copied_supply_path or not self.consolidated_supply_path:
            raise RuntimeError("Сначала выполните подготовку файлов.")
        self.supply_items = self.data_loader.load_supply_items(self.copied_supply_path)
        self.candidates = self.data_loader.load_candidates(self.consolidated_supply_path)

    def run_stage1(self, parent_widget=None) -> None:
        if not self.supply_items or not self.candidates:
            raise RuntimeError("Данные не загружены. Выполните подготовку и загрузку.")
        remaining_items, remaining_candidates = self._apply_mappings(self.supply_items, self.candidates)
        found, remaining, updated_candidates = self.stage1.run(
            remaining_items, remaining_candidates, parent_widget
        )
        mapped_items = [item for item in self.supply_items if item not in remaining_items]
        self.found_stage1 = found + mapped_items
        self.supply_items = remaining
        self.candidates = updated_candidates

    def run_stage2(self, parent_widget) -> None:
        if not self.supply_items or not self.candidates:
            raise RuntimeError("Данные не загружены.")
        stage2 = Stage2(parent_widget, logger=self.logger)
        self.found_stage2, self.supply_items, self.candidates = stage2.run(
            self.supply_items, self.candidates
        )

    def run_stage3(self, parent_widget) -> None:
        if not self.supply_items or not self.candidates:
            raise RuntimeError("Данные не загружены.")
        stage3 = Stage3(parent_widget, logger=self.logger)
        self.final_items = stage3.run(self.supply_items, self.candidates)

    def generate_report(self, output_dir: str) -> None:
        if not self.final_items:
            raise RuntimeError("Нет финальных данных. Выполните этап 3.")

        all_items = []
        all_items.extend(self.found_stage1)
        all_items.extend(self.found_stage2)
        all_items.extend(self.final_items)

        self.report_generator.generate(all_items, Path(output_dir), self.candidates)