import re
import statistics
import requests
from urllib.parse import urlparse

BASE = "https://www.sheypoor.com/api/v10.0.0"
SEARCH_URL = BASE + "/search/mazandaran/car"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/vnd.api+json",
    "Referer": "https://www.sheypoor.com/"
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def clean_number(value):
    if value is None:
        return None

    trans = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    value = str(value).translate(trans)
    digits = re.sub(r"[^\d]", "", value)

    return int(digits) if digits else None


def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("ي", "ی").replace("ك", "ک")
    value = value.replace("\u200c", "")
    value = value.replace(" ", "")
    return value


def get_attrs(ad):
    return ad.get("attributes") or {}


def get_full_attrs(ad):
    """
    پشتیبانی از هر دو ساختار API:
    1) fullAttributes در نتایج جست‌وجو
    2) attributes.attributes در جزئیات آگهی
    """
    a = get_attrs(ad)

    result = (
        ad.get("fullAttributes")
        or a.get("fullAttributes")
        or a.get("attributes")
        or []
    )

    if isinstance(result, dict):
        return result

    if isinstance(result, list):
        output = {}

        for item in result:
            if not isinstance(item, dict):
                continue

            key = item.get("key")
            value = item.get("value")

            if key:
                output[str(key).strip()] = value

        return output

    return {}


def get_price(a):
    prices = a.get("price") or []

    if not isinstance(prices, list) or not prices:
        return None

    p = prices[0]

    if not isinstance(p, dict):
        return None

    amount = p.get("amount")

    if amount is None or "توافقی" in str(amount):
        return None

    value = clean_number(amount)
    currency = str(p.get("currency", "تومان"))

    if value and "ریال" in currency:
        value //= 10

    return value


def get_listing_id(url):
    match = re.search(
        r"(?:/v/|/listings/)(?:[^/?]*-)?(\d+)",
        url
    )

    if not match:
        match = re.search(r"(\d{7,})", url)

    if not match:
        raise ValueError("شناسه آگهی از لینک استخراج نشد")

    return match.group(1)


def valid_sheypoor_url(url):
    parsed = urlparse(url)

    return (
        parsed.scheme == "https"
        and parsed.hostname in ("sheypoor.com", "www.sheypoor.com")
    )


def get_value(full, *keys):
    for key in keys:
        value = full.get(key)

        if value not in (None, ""):
            return value

    return None


def fetch_listing(url):
    if not valid_sheypoor_url(url):
        raise ValueError("لطفاً لینک معتبر و امن شیپور وارد کن.")

    listing_id = get_listing_id(url)

    response = SESSION.get(
        f"{BASE}/listings/{listing_id}",
        timeout=30
    )
    response.raise_for_status()

    data = response.json().get("data") or {}
    a = data.get("attributes") or {}

    full = get_full_attrs(data)

    title = a.get("title", "")
    description = a.get("description", "")

    # اگر اطلاعات مدل یا سال ناقص بود، از عنوان و توضیحات کمک می‌گیریم.
    if not get_value(full, "سال تولید (چهار رقمی)", "سال تولید"):
        years = re.findall(
            r"\b(?:13|14)\d{2}\b",
            title + " " + description
        )

        if years:
            full["سال تولید (چهار رقمی)"] = years[0]

    if not get_value(full, "مدل خودرو"):
        if "206" in title:
            if re.search(r"تیپ\s*2", title):
                full["مدل خودرو"] = "206 (تیپ2)"
            elif re.search(r"تیپ\s*5", title):
                full["مدل خودرو"] = "206 (تیپ5)"
            elif re.search(
                r"\b(sd|v8|v9|v10)\b|صندوقدار",
                title,
                re.I
            ):
                full["مدل خودرو"] = "206 SD"
            else:
                full["مدل خودرو"] = "206"

    year = clean_number(
        get_value(full, "سال تولید (چهار رقمی)", "سال تولید")
    )

    km = clean_number(
        get_value(full, "کیلومتر", "کارکرد")
    )

    return {
        "id": listing_id,
        "title": title,
        "url": a.get("url") or url,
        "price": get_price(a),
        "location": a.get("location", ""),
        "description": description,
        "year": year,
        "km": km,
        "model": get_value(full, "مدل خودرو") or title,
        "color": get_value(full, "رنگ"),
        "body": get_value(full, "وضعیت بدنه"),
        "front_chassis": get_value(full, "وضعیت شاسی جلو"),
        "rear_chassis": get_value(full, "وضعیت شاسی عقب"),
        "gearbox": get_value(full, "گیربکس"),
        "fuel": get_value(full, "نوع سوخت"),
        "full": full
    }


def model_query(car):
    model = str(car.get("model") or "")
    title = str(car.get("title") or "")
    source = normalize_text(model + " " + title)

    if "206" in source:
        if "تیپ2" in source:
            return "206 تیپ2"

        if "تیپ5" in source:
            return "206 تیپ5"

        if any(x in source for x in ("sd", "صندوقدار", "v8", "v9", "v10")):
            return "206 sd"

        return "206"

    if "405" in source:
        return "پژو 405"

    if "پارس" in source:
        return "پژو پارس"

    if "سمند" in source:
        return "سمند"

    if "پراید" in source:
        return "پراید"

    if "ساینا" in source:
        return "ساینا"

    if "تیبا" in source:
        return "تیبا"

    if "کوییک" in source:
        return "کوییک"

    return " ".join(title.split()[:3])


def same_model(target, candidate):
    t = normalize_text(
        target.get("model") or target.get("title")
    )

    c = normalize_text(
        candidate.get("model") or candidate.get("title")
    )

    if not t or not c:
        return False

    if "206" in t:
        if "206" not in c:
            return False

        target_type2 = "تیپ2" in t
        target_type5 = "تیپ5" in t
        target_sd = any(x in t for x in ("sd", "صندوقدار", "v8", "v9", "v10"))

        candidate_type2 = "تیپ2" in c
        candidate_type5 = "تیپ5" in c
        candidate_sd = any(x in c for x in ("sd", "صندوقدار", "v8", "v9", "v10"))

        if target_type2 and (not candidate_type2 or candidate_type5 or candidate_sd):
            return False

        if target_type5 and (not candidate_type5 or candidate_type2 or candidate_sd):
            return False

        if target_sd and not candidate_sd:
            return False

        if not target_sd and not target_type2 and not target_type5 and candidate_sd:
            return False

        return True

    if "405" in t:
        return "405" in c

    if "پارس" in t:
        return "پارس" in c

    if "سمند" in t:
        return "سمند" in c

    if "پراید" in t:
        return "پراید" in c

    if "ساینا" in t:
        return "ساینا" in c

    if "تیبا" in t:
        return "تیبا" in c

    if "کوییک" in t:
        return "کوییک" in c

    target_words = [
        x for x in t.split("(")[0].split()
        if len(x) > 1
    ]

    return bool(target_words) and all(
        x in c for x in target_words[:2]
    )


def get_comparables(car, pages=5):
    query = model_query(car)
    found = {}

    for page in range(1, pages + 1):
        response = SESSION.get(
            SEARCH_URL,
            params={"q": query, "p": page},
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        ads = []

        for item in data.get("data", []):
            if item.get("type") == "normal":
                ads.append(item)

            elif item.get("type") == "special":
                nested = item.get("items") or []

                for nested_item in nested:
                    if nested_item.get("type") == "normal":
                        ads.append(nested_item)

        for ad in ads:
            ad_id = str(ad.get("id") or "")

            if not ad_id or ad_id == str(car["id"]):
                continue

            if ad_id in found:
                continue

            a = get_attrs(ad)
            full = get_full_attrs(ad)

            item = {
                "id": ad_id,
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "price": get_price(a),
                "location": a.get("location", ""),
                "year": clean_number(
                    get_value(full, "سال تولید (چهار رقمی)", "سال تولید")
                ),
                "km": clean_number(
                    get_value(full, "کیلومتر", "کارکرد")
                ),
                "model": get_value(full, "مدل خودرو") or a.get("title", ""),
                "color": get_value(full, "رنگ"),
                "body": get_value(full, "وضعیت بدنه"),
                "front_chassis": get_value(full, "وضعیت شاسی جلو"),
                "rear_chassis": get_value(full, "وضعیت شاسی عقب")
            }

            found[ad_id] = item

    results = []

    for item in found.values():
        price = item.get("price")

        if not price or price < 100_000_000:
            continue

        if not same_model(car, item):
            continue

        if car.get("year") and item.get("year"):
            if abs(car["year"] - item["year"]) > 2:
                continue

        results.append(item)

    # نزدیک‌ترین سال و کارکرد به خودروی هدف در ابتدای فهرست
    def relevance(item):
        year_gap = 99
        km_gap = 999999999

        if car.get("year") and item.get("year"):
            year_gap = abs(car["year"] - item["year"])

        if car.get("km") and item.get("km"):
            km_gap = abs(car["km"] - item["km"])

        return (year_gap, km_gap)

    results.sort(key=relevance)

    return results


def analyze_listing(url):
    car = fetch_listing(url)
    comps = get_comparables(car)

    prices = [
        item["price"]
        for item in comps
        if item.get("price")
    ]

    result = {
        "vehicle": car,
        "comparable_count": len(comps),
        "comparables": comps[:30],
        "market_median": None,
        "market_low": None,
        "market_high": None,
        "dealer_buy_range": None,
        "resale_range": None,
        "assessment": "داده مشابه کافی نیست"
    }

    if len(prices) < 3:
        result["warning"] = (
            "برای برآورد قابل اتکا حداقل ۳ آگهی مشابه لازم است."
        )
        return result

    median = int(statistics.median(prices))

    clean = [
        price for price in prices
        if median * 0.65 <= price <= median * 1.45
    ]

    if len(clean) >= 3:
        median = int(statistics.median(clean))
    else:
        clean = prices

    result["market_median"] = median
    result["market_low"] = int(median * 0.92)
    result["market_high"] = int(median * 1.08)

    result["dealer_buy_range"] = [
        int(median * 0.88),
        int(median * 0.92)
    ]

    result["resale_range"] = [
        int(median * 0.97),
        int(median * 1.02)
    ]

    asking = car.get("price")

    if asking:
        if asking <= median * 0.88:
            assessment = "قیمت آگهی پایین‌تر از بازار؛ کارشناسی ضروری است"

        elif asking <= median * 0.95:
            assessment = "قیمت قابل بررسی برای خرید"

        elif asking <= median * 1.05:
            assessment = "نزدیک به میانگین قیمت آگهی‌های مشابه"

        else:
            assessment = "قیمت بالاتر از میانگین آگهی‌های مشابه"

        result["assessment"] = assessment

    result["warning"] = (
        "برآورد بر اساس قیمت آگهی‌هاست، نه معاملات قطعی. "
        "وضعیت فنی، رنگ و شاسی باید حضوری کارشناسی شود."
    )

    return result
