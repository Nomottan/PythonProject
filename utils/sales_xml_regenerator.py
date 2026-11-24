"""
Генератор XML-филлера УПД для загрузки в СБИС.

Содержит два класса:
    UpdFillerItem      — позиция табличной части (наименование, КИЗы, GTIN).
    UpdFillerGenerator — сборка XML по моделям Seller/Signer.

Роль в программе:
    Заменяет «Уведомление о выкупе» дочернего проекта: документ
    собирается не из Excel-парсера, а из данных основной программы.
    Цены и суммы пишутся заглушкой 0.00 — сотрудник заполнит их
    в СБИС. КИЗы идут в ДопСведТов/НомСредИдентТов.
"""

import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from utils.parsers import FileNameParser
from utils.matchers import Matcher
from utils.excel_helper import WorkbookOpener
from utils.sales_file_generator import SalesFileKizReader
from utils.text_utils import TextUtils

@dataclass
class SalesXmlItem:
    """Позиция табличной части УПД.

    Поля:
        name — наименование товара.
        kizs — список КИЗов (по одному на единицу товара).
        gtin — GTIN товара (пустая строка, если неизвестен).
    """

    name: str
    kizs: list = field(default_factory=list)
    gtin: str = ""

class SalesXmlGenerator:
    """Генератор XML-филлера УПД.

    Назначение:
        Собирает XML УПД 5.03 из моделей Seller/Signer и списка
        позиций. Структура повторяет дочерний UTDInXML — СБИС её
        принимает. Отличия: ВерсПрог="Helper", КИЗы в
        ДопСведТов/НомСредИдентТов, цены — заглушка 0.00,
        ОснПер — БезДокОснПер=1.

    Публичный API:
        is_ip — тип контрагента по длине ИНН.
        group_items — строки Excel → позиции.
        generate — XML-строка.
        save — запись в файл windows-1251.
    """

    VERSION_FORM = "5.03"
    VERSION_PROG = "Helper"
    KND = "1115131"
    FUNCTION = "СЧФДОП"
    PO_FAKT_HZH = (
        "Документ об отгрузке товаров (выполнении работ), "
        "передаче имущественных прав (документ об оказании услуг)"
    )
    NAIM_DOK_OPR = (
        "Счет-фактура и документ об отгрузке товаров "
        "(выполнении работ), передаче имущественных прав "
        "(документ об оказании услуг)"
    )
    OKEI = "796"
    UNIT_NAME = "шт"
    PRICE_STUB = "0.00"
    DEFAULT_VAT_RATE = 5
    OSN_BEZ_DOK = "1"

    # ---------- Тип контрагента ----------

    @staticmethod
    def is_ip(seller) -> bool:
        """Определяет, ИП ли контрагент.

        Вход: seller — Seller.
        Выход: True, если ИНН из 12 цифр (ИП), иначе False (ООО).

        Роль: ИНН физлица/ИП — 12 цифр, юрлица — 10. Явного
              поля type_ у Seller нет.
        """
        inn = getattr(seller, "inn", "") or ""
        return len(str(inn).strip()) == 12

    # ---------- Данные контрагента ----------

    @staticmethod
    def _company_name(seller) -> str:
        """Возвращает полное наименование для XML.

        Вход: seller — Seller.
        Выход: company, если непустое; иначе name.

        Роль: у ИП company = «ИП ГААК НАТАЛЬЯ СЕРГЕЕВНА»,
              у ООО — полное наименование. name — короткое,
              для документов не подходит.
        """
        company = (getattr(seller, "company", "") or "").strip()
        if company:
            return company
        return (getattr(seller, "name", "") or "").strip()

    @staticmethod
    def _ip_fio_parts(seller) -> tuple:
        """Разбирает ФИО ИП на части.

        Вход: seller — Seller (ИП).
        Выход: (Фамилия, Имя, Отчество), капитализированные.

        Роль: берём company, отбрасываем ведущее «ИП»,
              делим через TextUtils.split_fio, каждую часть
              нормализуем через sanitize_fio_part.
        """
        company = SalesXmlGenerator._company_name(seller)
        tokens = company.split()
        if tokens and tokens[0].upper() == "ИП":
            tokens = tokens[1:]
        parts = TextUtils.split_fio(" ".join(tokens))

        last = parts[0] if len(parts) > 0 else ""
        first = parts[1] if len(parts) > 1 else ""
        middle = parts[2] if len(parts) > 2 else ""

        return (
            TextUtils.sanitize_fio_part(last),
            TextUtils.sanitize_fio_part(first),
            TextUtils.sanitize_fio_part(middle),
        )

    @staticmethod
    def _vat_rate(seller) -> str:
        """Возвращает ставку НДС для НалСт.

        Вход: seller — Seller.
        Выход: строка вида "5%".

        Роль: ставка берётся от продавца. Нет поля tax →
              DEFAULT_VAT_RATE (как в SalesFileGenerator).
        """
        tax = getattr(seller, "tax", None)
        if tax is None:
            tax = SalesXmlGenerator.DEFAULT_VAT_RATE
        return f"{int(tax)}%"

    # ---------- Позиции ----------

    @staticmethod
    def group_items(rows) -> list:
        """Группирует строки Excel в позиции УПД.

        Вход: rows — список кортежей (product_name, kiz, gtin).
        Выход: list[UpdFillerItem].

        Роль: одна позиция на товар. КИЗы собираются в список,
              GTIN берётся первым непустым. Порядок — по первому
              появлению товара.
        """
        grouped = {}
        order = []

        for product_name, kiz, gtin in rows:
            name = (product_name or "").strip()
            if not name:
                name = "Товар без наименования"
            key = TextUtils.normalize(name)

            if key not in grouped:
                grouped[key] = SalesXmlItem(name=name)
                order.append(key)

            item = grouped[key]

            kiz = (kiz or "").strip()
            if kiz:
                item.kizs.append(kiz)

            gtin = (gtin or "").strip()
            if gtin and not item.gtin:
                item.gtin = gtin

        return [grouped[k] for k in order]

    # ---------- Сборка XML ----------

    @staticmethod
    def generate(seller, buyer, signer, items,
                 doc_number="", doc_date=None) -> str:
        """Собирает XML-строку УПД.

        Вход:
            seller — Seller-продавец (он же грузоотправитель).
            buyer — Seller-покупатель (он же грузополучатель).
            signer — Signer (ФИО + должность).
            items — list[UpdFillerItem].
            doc_number — НомерДок; "" по умолчанию.
            doc_date — ДатаДок; None → сегодня.

        Выход: XML-строка с декларацией windows-1251.

        Роль: структура повторяет дочерний генератор UTDInXML.
        """
        now = datetime.now()
        date_value = doc_date or now.strftime("%d.%m.%Y")

        root = ET.Element("Файл", {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "ИдФайл": SalesXmlGenerator._build_id_file(
                buyer, seller, date_value,
            ),
            "ВерсФорм": SalesXmlGenerator.VERSION_FORM,
            "ВерсПрог": SalesXmlGenerator.VERSION_PROG,
        })

        doc = ET.SubElement(root, "Документ", {
            "КНД": SalesXmlGenerator.KND,
            "Функция": SalesXmlGenerator.FUNCTION,
            "ПоФактХЖ": SalesXmlGenerator.PO_FAKT_HZH,
            "НаимДокОпр": SalesXmlGenerator.NAIM_DOK_OPR,
            "ДатаИнфПр": now.strftime("%d.%m.%Y"),
            "ВремИнфПр": now.strftime("%H.%M.%S"),
            "НаимЭконСубСост": SalesXmlGenerator._company_name(seller),
        })

        sv_sch_fakt = ET.SubElement(doc, "СвСчФакт", {
            "НомерДок": doc_number or "",
            "ДатаДок": date_value,
        })

        sv_prod = ET.SubElement(sv_sch_fakt, "СвПрод")
        SalesXmlGenerator._build_party_body(sv_prod, seller)

        gruz_ot = ET.SubElement(sv_sch_fakt, "ГрузОт")
        ET.SubElement(gruz_ot, "ОнЖе").text = "он же"

        gruz_poluch = ET.SubElement(sv_sch_fakt, "ГрузПолуч")
        SalesXmlGenerator._build_party_body(gruz_poluch, buyer)

        sv_pokup = ET.SubElement(sv_sch_fakt, "СвПокуп")
        SalesXmlGenerator._build_party_body(sv_pokup, buyer)

        ET.SubElement(sv_sch_fakt, "ДенИзм", {
            "КодОКВ": "643",
            "НаимОКВ": "Российский рубль",
        })

        vat_rate = SalesXmlGenerator._vat_rate(seller)
        tabl = ET.SubElement(doc, "ТаблСчФакт")

        for idx, item in enumerate(items, start=1):
            count = len(item.kizs) if item.kizs else 1
            sved_tov = ET.SubElement(tabl, "СведТов", {
                "НомСтр": str(idx),
                "НаимТов": item.name,
                "ОКЕИ_Тов": SalesXmlGenerator.OKEI,
                "НаимЕдИзм": SalesXmlGenerator.UNIT_NAME,
                "КолТов": str(count),
                "ЦенаТов": SalesXmlGenerator.PRICE_STUB,
                "СтТовБезНДС": SalesXmlGenerator.PRICE_STUB,
                "НалСт": vat_rate,
                "СтТовУчНал": SalesXmlGenerator.PRICE_STUB,
            })

            dop_attrs = {}
            if item.gtin:
                dop_attrs["КодТов"] = item.gtin
            dop = ET.SubElement(sved_tov, "ДопСведТов", dop_attrs)

            if item.kizs:
                nom = ET.SubElement(dop, "НомСредИдентТов")
                for kiz in item.kizs:
                    ET.SubElement(nom, "КИЗ").text = kiz

            akciz = ET.SubElement(sved_tov, "Акциз")
            ET.SubElement(akciz, "БезАкциз").text = "без акциза"

            sum_nal = ET.SubElement(sved_tov, "СумНал")
            ET.SubElement(sum_nal, "СумНал").text = (
                SalesXmlGenerator.PRICE_STUB
            )

        vsego = ET.SubElement(tabl, "ВсегоОпл", {
            "СтТовБезНДСВсего": SalesXmlGenerator.PRICE_STUB,
            "СтТовУчНалВсего": SalesXmlGenerator.PRICE_STUB,
        })
        sum_nal_vsego = ET.SubElement(vsego, "СумНалВсего")
        ET.SubElement(sum_nal_vsego, "СумНал").text = (
            SalesXmlGenerator.PRICE_STUB
        )

        sv_prod_per = ET.SubElement(doc, "СвПродПер")
        sv_per = ET.SubElement(sv_prod_per, "СвПер", {
            "СодОпер": "Товары переданы",
            "ДатаПер": date_value,
        })
        ET.SubElement(sv_per, "БезДокОснПер").text = (
            SalesXmlGenerator.OSN_BEZ_DOK
        )

        SalesXmlGenerator._build_signer(doc, seller, signer, now)

        ET.indent(root, space=" ")
        xml_str = ET.tostring(root, encoding="unicode")
        return '<?xml version="1.0" encoding="windows-1251"?>\n' + xml_str

    @staticmethod
    def regenerate(sales_dir, sellers, signers, logger=None) -> dict:
        """Формирует XML-файлы рядом с готовыми файлами продаж.

        Вход:
            sales_dir — конечная папка продаж («Продажи»), Path или str.
            sellers — список Seller (для поиска отправителя/получателя
                      по имени из имени файла).
            signers — список Signer. Берётся первый; пусто → XML
                      не создаются.
            logger — LoggerV2 или None.

        Выход:
            dict со статистикой:
                files_total   — найдено .xlsx
                files_created — создано .xml
                files_skipped — пропущено (нет продавца / нет позиций)
                items_total   — всего позиций в созданных XML
                no_signer     — True, если подписанта не было

        Роль:
            Вызывается один раз в конце обработки, ПОСЛЕ разрешения
            дублей: в папке уже лежат финальные .xlsx, XML строится
            ровно из них. Имя .xml повторяет имя .xlsx (with_suffix),
            поэтому маски файлов не множатся.
        """
        stats = {
            "files_total": 0,
            "files_created": 0,
            "files_skipped": 0,
            "items_total": 0,
            "no_signer": False,
        }

        signer = signers[0] if signers else None
        if signer is None:
            stats["no_signer"] = True
            if logger is not None:
                logger.warning(
                    "Нет подписанта в справочнике сотрудников — "
                    "XML-файлы не созданы"
                )
            return stats

        base = Path(sales_dir)
        if not base.is_dir():
            if logger is not None:
                logger.warning(
                    f"Папка продаж не найдена: {base} — XML не созданы"
                )
            return stats

        for file_path in sorted(base.glob("*.xlsx")):
            stats["files_total"] += 1

            try:
                parsed_from, parsed_to, _inn = (
                    FileNameParser.parse_sales(file_path.name)
                )
                seller = Matcher.first(
                    sellers, "name", parsed_from,
                    transform=TextUtils.sanitize_filename,
                )
                buyer = Matcher.first(
                    sellers, "name", parsed_to,
                    transform=TextUtils.sanitize_filename,
                )

                if seller is None or buyer is None or seller is buyer:
                    stats["files_skipped"] += 1
                    if logger is not None:
                        logger.warning(
                            f"{file_path.name}: не удалось определить "
                            f"пару продавцов — XML не создан"
                        )
                    continue

                rows = SalesXmlGenerator._read_sale_rows(
                    file_path, logger,
                )
                items = SalesXmlGenerator.group_items(rows)
                items = [item for item in items if item.kizs]

                if not items:
                    stats["files_skipped"] += 1
                    if logger is not None:
                        logger.debug(
                            f"{file_path.name}: нет строк с КИЗ — "
                            f"XML не создан"
                        )
                    continue

                xml_string = SalesXmlGenerator.generate(
                    seller, buyer, signer, items,
                )
                xml_path = file_path.with_suffix(".xml")
                SalesXmlGenerator.save(xml_string, xml_path)

                stats["files_created"] += 1
                stats["items_total"] += len(items)
                if logger is not None:
                    logger.debug(
                        f"{file_path.name} → {xml_path.name}: "
                        f"позиций {len(items)}"
                    )
            except Exception as e:
                stats["files_skipped"] += 1
                if logger is not None:
                    logger.warning(
                        f"{file_path.name}: XML не создан ({e})"
                    )
                continue

        if logger is not None:
            logger.info(
                f"\nXML по файлам продаж: создано "
                f"{stats['files_created']} из {stats['files_total']}, "
                f"пропущено {stats['files_skipped']}, "
                f"позиций {stats['items_total']}"
            )
        return stats

    # ---------- Служебное ---------

    @staticmethod
    def _read_sale_rows(file_path, logger=None) -> list:
        """Читает строки файла продаж.

        Вход:
            file_path — путь к .xlsx.
            logger — LoggerV2 или None.

        Выход: список кортежей (наименование, КИЗ, GTIN).
               Пустой список при ошибке открытия.

        Роль: колонки заданы SalesFileKizReader — единый источник
              индексов для всех, кто читает файлы продаж.
        """
        wb = WorkbookOpener.open(
            file_path, logger=logger, read_only=True,
        )
        if wb is None:
            return []

        try:
            sheet = wb.active
            raw_rows = list(
                sheet.iter_rows(min_row=2, values_only=True)
            )
        finally:
            try:
                wb.close()
            except Exception:
                pass

        name_col = SalesFileKizReader.PRODUCT_COLUMN_INDEX
        kiz_col = SalesFileKizReader.KIZ_COLUMN_INDEX
        gtin_col = SalesFileKizReader.GTIN_COLUMN_INDEX

        rows = []
        for raw in raw_rows:
            if raw is None:
                continue
            name = raw[name_col] if len(raw) > name_col else None
            kiz = raw[kiz_col] if len(raw) > kiz_col else None
            gtin = raw[gtin_col] if len(raw) > gtin_col else None
            rows.append((name, kiz, gtin))

        return rows

    @staticmethod
    def _find_column(header: list, variants: tuple):
        """Ищет индекс колонки по вхождениям в заголовок.

        Вход:
            header — нормализованные заголовки (lower, strip).
            variants — варианты подстрок.

        Выход: int или None.
        """
        for index, title in enumerate(header):
            for variant in variants:
                if variant in title:
                    return index
        return None

    @staticmethod
    def _build_party_body(parent, seller) -> None:
        """Добавляет ИдСв и Адрес контрагента.

        Вход:
            parent — родительский ET-элемент (СвПрод/ГрузПолуч/…).
            seller — Seller.

        Роль: СвИП для ИП (ФИО из company без «ИП»),
              СвЮЛУч для ООО (КПП только если заполнен).
        """
        id_sv = ET.SubElement(parent, "ИдСв")
        inn = str(getattr(seller, "inn", "") or "").strip()

        if SalesXmlGenerator.is_ip(seller):
            sv_ip = ET.SubElement(id_sv, "СвИП", {"ИННФЛ": inn})
            last, first, middle = SalesXmlGenerator._ip_fio_parts(seller)
            fio_attrs = {}
            if last:
                fio_attrs["Фамилия"] = last
            if first:
                fio_attrs["Имя"] = first
            if middle:
                fio_attrs["Отчество"] = middle
            ET.SubElement(sv_ip, "ФИО", fio_attrs)
        else:
            attrs = {
                "ИННЮЛ": inn,
                "НаимОрг": SalesXmlGenerator._company_name(seller),
            }
            kpp = str(getattr(seller, "kpp", "") or "").strip()
            if kpp:
                attrs["КПП"] = kpp
            ET.SubElement(id_sv, "СвЮЛУч", attrs)

        address = getattr(seller, "address", None)
        if address is None:
            return

        pairs = (
            ("index", "Индекс"),
            ("region_code", "КодРегион"),
            ("region_name", "НаимРегион"),
            ("city", "Город"),
            ("settlement", "НаселПункт"),
            ("street", "Улица"),
            ("house", "Дом"),
            ("building", "Корпус"),
        )
        addr_attrs = {}
        for attr_name, tag_name in pairs:
            value = str(getattr(address, attr_name, "") or "").strip()
            if value:
                addr_attrs[tag_name] = value

        if addr_attrs:
            addr = ET.SubElement(parent, "Адрес")
            ET.SubElement(addr, "АдрРФ", addr_attrs)

    @staticmethod
    def _build_signer(doc, seller, signer, now) -> None:
        """Добавляет узел Подписант.

        Вход:
            doc — ET-элемент Документ.
            seller — Seller (для ТипПодпис).
            signer — Signer.
            now — datetime.

        Роль: ФИО подписанта разбирается через TextUtils.split_fio,
              должность — signer.role.
        """
        podp_attrs = {
            "ТипПодпис": "1" if SalesXmlGenerator.is_ip(seller) else "2",
            "ДатаПодДок": now.strftime("%d.%m.%Y"),
            "СпосПодтПолном": "1",
        }

        position = ""
        if signer is not None:
            position = (getattr(signer, "role", "") or "").strip()
        if position:
            podp_attrs["Должн"] = position

        podp = ET.SubElement(doc, "Подписант", podp_attrs)

        name = ""
        if signer is not None:
            name = getattr(signer, "name", "") or ""
        parts = TextUtils.split_fio(name)

        fio_attrs = {}
        if len(parts) > 0:
            fio_attrs["Фамилия"] = TextUtils.sanitize_fio_part(parts[0])
        if len(parts) > 1:
            fio_attrs["Имя"] = TextUtils.sanitize_fio_part(parts[1])
        if len(parts) > 2:
            fio_attrs["Отчество"] = TextUtils.sanitize_fio_part(parts[2])

        ET.SubElement(podp, "ФИО", fio_attrs)

    @staticmethod
    def _build_id_file(buyer, seller, date_str) -> str:
        """Собирает ИдФайл по образцу дочернего проекта.

        Вход: buyer, seller — Seller; date_str — "ДД.ММ.ГГГГ".
        Выход: строка ИдФайл.

        Роль: СБИС перегенерирует идентификатор, поэтому формат
              сохранён как у дочернего — главное уникальность.
        """
        try:
            date_iso = datetime.strptime(
                date_str, "%d.%m.%Y",
            ).strftime("%Y%m%d")
        except ValueError:
            date_iso = datetime.now().strftime("%Y%m%d")

        buyer_inn = str(getattr(buyer, "inn", "") or "").strip()
        seller_inn = str(getattr(seller, "inn", "") or "").strip()
        kpp = str(getattr(buyer, "kpp", "") or "").strip() or "__"

        return (
            f"ON_NSCHFDOPPR_{buyer_inn}_{kpp}_{seller_inn}_"
            f"{date_iso}_{uuid.uuid4()}_0_0_0_0_0_00"
        )

    # ---------- Сохранение ----------

    @staticmethod
    def save(xml_string, path) -> None:
        """Пишет XML в файл windows-1251.

        Вход: xml_string — строка из generate; path — путь.
        Выход: нет.
        Роль: errors="replace" — чтобы редкий символ не ронял
              запись (как в дочернем проекте).
        """
        with open(
            path, "w", encoding="windows-1251",
            errors="replace", newline="",
        ) as f:
            f.write(xml_string)