import pycountry

VALID_TITLES = {"GM", "IM", "FM", "CM", "WGM", "WIM", "WFM", "WCM"}

TITLE_WORD_TO_CODE = {
    "GRANDMASTER": "GM",
    "INTERNATIONAL MASTER": "IM",
    "FIDE MASTER": "FM",
    "CANDIDATE MASTER": "CM",
    "WOMAN GRANDMASTER": "WGM",
    "WOMAN INTERNATIONAL MASTER": "WIM",
    "WOMAN FIDE MASTER": "WFM",
    "WOMAN CANDIDATE MASTER": "WCM",
}

COUNTRY_OVERRIDES = {
    "USA": "US",
    "U.S.A.": "US",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "UK": "GB",
    "U.K.": "GB",
    "UNITED KINGDOM": "GB",
    "ENGLAND": "GB",
    "SCOTLAND": "GB",
    "WALES": "GB",
    "UAE": "AE",
    "UNITED ARAB EMIRATES": "AE",
    "SOUTH KOREA": "KR",
    "NORTH KOREA": "KP",
    "KOREA": "KR",
    "VIET NAM": "VN",
    "CZECH REPUBLIC": "CZ",
}

def clean_fide_title(raw) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""

    upper = s.upper()
    if upper in {"UNTITLED", "NONE", "NO TITLE", "N/A", "-", "NULL"}:
        return ""

    if upper in TITLE_WORD_TO_CODE:
        return TITLE_WORD_TO_CODE[upper]

    if upper in VALID_TITLES:
        return upper

    for code in VALID_TITLES:
        if code in upper:
            return code

    return ""

def iso2_to_flag(iso2: str) -> str:
    if not iso2 or len(iso2) != 2:
        return ""
    iso2 = iso2.upper()
    if not ("A" <= iso2[0] <= "Z" and "A" <= iso2[1] <= "Z"):
        return ""
    return chr(0x1F1E6 + ord(iso2[0]) - ord("A")) + chr(0x1F1E6 + ord(iso2[1]) - ord("A"))

def country_name_to_iso2(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    if not n:
        return ""

    up = n.upper()
    if up in COUNTRY_OVERRIDES:
        return COUNTRY_OVERRIDES[up]

    try:
        c = pycountry.countries.get(name=n)
        if c and getattr(c, "alpha_2", None):
            return c.alpha_2
    except Exception:
        pass

    try:
        matches = pycountry.countries.search_fuzzy(n)
        if matches:
            c = matches[0]
            return getattr(c, "alpha_2", "") or ""
    except Exception:
        pass

    return ""

def country_to_flag(country_name: str) -> str:
    return iso2_to_flag(country_name_to_iso2(country_name))