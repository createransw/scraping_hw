import re
from datetime import datetime
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup


class CssParser:
    def __init__(self):
        self._teams = {}

    def parse(self, content, cur_page_url):
        soup = BeautifulSoup(content, "html.parser")

        ln = soup.select_one("body div .infobox")["data-name"]

        if "Соревнование" in ln:
            return None, self._parse_chempoinship(soup, cur_page_url)

        if "Сборная" in ln:
            return None, self._parse_team(soup, cur_page_url)

        return self._parse_player(soup, cur_page_url), []

    def _parse_chempoinship(self, root, cur_page_url):
        self._teams = {}
        table = root.select("table.standard tr td:nth-child(1) > a")

        links = [ln.get("href") for ln in table]
        parsed = urlparse(cur_page_url)
        links = [urljoin(parsed.scheme + "://" + parsed.netloc, ln) for ln in links]

        return links

    def _parse_team(self, root, cur_page_url):
        parsed = urlparse(cur_page_url)

        pointers = []
        table = root.find("span", id=re.compile("^Текущий_состав"))
        if not table:
            table = root.find("span", id=re.compile("^Состав"))
        if table:
            pointers.append(table.parent)
        table = root.find("span", id=re.compile("^Недавние_вызовы"))
        if table:
            pointers.append(table.parent)

        links = []
        for pointer in pointers:
            while not (pointer.name and pointer.name == "table"):
                pointer = pointer.next_sibling

            table = pointer.tbody.select("tr")
            table = [ln.select_one("td:nth-child(3) > a") for ln in table]

            links_tmp = [ln.get("href") for ln in table if ln]
            links_tmp = [ln for ln in links_tmp if "index.php" not in ln]
            links += links_tmp


        links = [urljoin(parsed.scheme + "://" + parsed.netloc, ln) for ln in links]

        ln = unquote(cur_page_url).split("/")[-1].replace("_", " ").strip()
        for l in links:
            self._teams[l] = ln

        return links

    def _parse_player(self, root, cur_page_url):
        info = {}

        info["url"] = cur_page_url

        self._find_name(root, info)
        self._read_infobox(root, info)
        self._transform_height(info)
        self._find_club_caps(root, info)
        self._find_national_caps(root, info)
        self._find_national_team(cur_page_url, info)
        self._transform_birth(info)

        return info

    def _find_name(self, root, info) -> None:
        name = root.select_one(".infobox tbody tr .ts_Спортсмен_имя").text
        bracket = name.rfind("(")
        if bracket > 0:
            name = name[:bracket]
        info["name"] = list(map(str.strip, name.rsplit(" ", 1)))[::-1]

    def _read_infobox(self, root, info) -> None:
        info["height"] = root.select_one('span[data-wikidata-property-id="P2048"]').text.strip()
        info["position"] = root.select_one('span[data-wikidata-property-id="P413"]').text.strip()
        info["current_club"] = root.select_one('span[data-wikidata-property-id="P54"]').text.strip()
        info["birth"] = root.select_one('span[data-wikidata-property-id="P569"]').text.strip()


    def _transform_height(self, info) -> None:
        if "height" not in info:
            return
        info["height"] = re.findall(".*?[[ ]", info["height"])[0]
        info["height"] = int(re.findall("[0-9]+", info["height"])[-1])

    def _find_club_caps(self, root, info) -> None:
        pointers = root.select(".infobox table tbody tr")
        i = 0
        while "Клубная карьера" not in pointers[i].text:
            i += 1

        i += 1
        pointer = pointers[i]

        from_table = 0
        sc_from_table = 0
        cell = pointer.select_one("td:nth-child(3)")
        while cell:
            ln, sc = cell.text.strip().split("(")
            sc = re.findall(".*?[)/]", sc)[0][:-1]
            sc = re.sub("[−–]", "-", sc)
            if "?" in sc:
                sc = "0"
            if ln.strip().isdigit():
                from_table += int(ln)
                sc_from_table += int(sc)
            i += 1
            if i >= len(pointers):
                break
            pointer = pointers[i]
            cell = pointer.select_one("td:nth-child(3)")

        tables = root.select("table:not(.infobox) tbody tr")
        from_cell = 0
        sc_from_cell = 0
        for t in tables:
            rows = t.select("th")
            if len(rows) < 2:
                continue
            if rows[0].text.strip() != "Клуб" and rows[1].text.strip() != "Клуб":
                continue

            t_temp = t.parent.select_one("tr:last-child").select_one("th:last-child")
            if not t_temp:
                t_temp = t.parent.select_one("tr:last-child").select_one("td:last-child")
            t = t_temp

            t = t.previous_sibling
            if not t.name:
                t = t.previous_sibling
            if "−" in t.text or "-" in t.text:
                t = t.previous_sibling
                if not t.name:
                    t = t.previous_sibling
            from_cell = int("0" if "?" in t.text else t.text.strip())
            t = t.next_sibling
            if not t.name:
                t = t.next_sibling
            if "?" in t.text:
                sc_from_cell = 0
            else:
                sc_from_cell = int(re.sub("[−-]", "-", t.text.strip()))
            break

        info["club_caps"] = max(from_table, from_cell)
        if sc_from_table < 0 or sc_from_cell < 0:
            info["club_conceded"] = abs(min(sc_from_cell, sc_from_table))
            info["club_scored"] = 0
        else:
            info["club_conceded"] = 0
            info["club_scored"] = max(sc_from_table, sc_from_cell)

    def _find_national_caps(self, root, info) -> None:
        pointers = root.select(".infobox table tbody tr")
        i = 0
        pointer = pointers[i]
        while "Национальная сборная" not in pointers[i].text:
            i += 1
            if i >= len(pointers):
                info["national_caps"] = 0
                info["national_conceded"] = 0
                info["national_scored"] = 0
                return

        i += 1

        from_table = 0
        sc_from_table = 0
        cell = pointers[i].select_one("td:nth-child(2)")
        while cell:
            if "до" not in cell.text:
                cell = cell.next_sibling
                if not cell.name:
                    cell = cell.next_sibling
                ln, sc = cell.text.strip().split("(")
                sc = re.findall(".*?[)/]", sc)[0][:-1]
                sc = re.sub("[−–]", "-", sc)
                if "?" in sc:
                    sc = "0"
                if ln.strip().isdigit():
                    from_table += int(ln)
                sc_from_table += int(sc)

            i += 1
            if i >= len(pointers):
                break
            cell = pointers[i].select_one("td:nth-child(2)")

        info["national_caps"] = from_table
        if sc_from_table < 0:
            info["national_conceded"] = abs(sc_from_table)
            info["national_scored"] = 0
        else:
            info["national_conceded"] = 0
            info["national_scored"] = sc_from_table

    def _find_national_team(self, url, info):
        info["national_team"] = self._teams[url]
        del self._teams[url]

    def _transform_birth(self, info):
        ln = info["birth"].split("(")[0].split("[")[0].strip()
        dictionary = {
            "января": "01",
            "февраля": "02",
            "марта": "03",
            "апреля": "04",
            "мая": "05",
            "июня": "06",
            "июля": "07",
            "августа": "08",
            "сентября": "09",
            "октября": "10",
            "ноября": "11",
            "декабря": "12",
        }
        for m in dictionary.items():
            ln = ln.replace(m[0], m[1])
        birth = datetime.strptime(ln, "%d %m %Y")
        info["birth"] = int(datetime.timestamp(birth))
