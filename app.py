from flask import Flask, request, render_template_string
import requests, re, json, html, sqlite3, os
from bs4 import BeautifulSoup
from datetime import datetime

app = Flask(__name__)
DB = os.path.expanduser("~/mashinyar.db")
HEADERS = {"User-Agent": "Mozilla/5.0"}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def setup():
    c = db()
    c.execute("""
    CREATE TABLE IF NOT EXISTS cars (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      car TEXT, year TEXT, km TEXT, city TEXT,
      price INTEGER, market INTEGER, value INTEGER,
      buy INTEGER, profit INTEGER, status TEXT,
      created TEXT
    )""")
    columns = [x[1] for x in c.execute("PRAGMA table_info(cars)")]
    for name, typ in [
        ("source_url", "TEXT"),
        ("description", "TEXT"),
        ("color", "TEXT"),
        ("gear", "TEXT")
    ]:
        if name not in columns:
            c.execute(f"ALTER TABLE cars ADD COLUMN {name} {typ}")
    c.commit()
    c.close()

setup()

def digits(s):
    return str(s).translate(str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    ))

def number(s):
    if not s:
        return None
    s = digits(str(s))
    found = re.sub(r"[^\d]", "", s)
    return int(found) if found else None

def find(pattern, text):
    m = re.search(pattern, text, re.S)
    return html.unescape(m.group(1)) if m else None

def get_sheypoor(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue

        items = data if isinstance(data, list) else [data]

        for item in items:
            if not isinstance(item, dict):
                continue
            vehicle = item.get("mainEntity", item)
            if not isinstance(vehicle, dict):
                continue
            if "Vehicle" not in str(vehicle.get("@type", "")):
                continue

            offers = vehicle.get("offers", {})
            mileage = vehicle.get("mileageFromOdometer", {})
            brand = vehicle.get("brand", {})

            price = offers.get("price", offers.get("Price"))
            if price:
                price = int(float(price))
                if offers.get("priceCurrency") == "IRR":
                    price //= 10

            city = ""
            for sc in soup.find_all("script", type="application/ld+json"):
                try:
                    d = json.loads(sc.string or sc.get_text())
                    if isinstance(d, dict) and d.get("@type") == "BreadcrumbList":
                        names = [
                            x.get("name", "")
                            for x in d.get("itemListElement", [])
                        ]
                        city = "، ".join(names[:2])
                except Exception:
                    pass

            return {
                "site": "شیپور",
                "title": vehicle.get("name"),
                "brand": brand.get("name") if isinstance(brand, dict) else brand,
                "year": vehicle.get("vehicleModelDate"),
                "km": number(mileage.get("value")) if isinstance(mileage, dict) else None,
                "price": price,
                "city": city,
                "color": vehicle.get("color"),
                "gear": vehicle.get("vehicleTransmission"),
                "description": vehicle.get("description"),
                "url": vehicle.get("url")
            }
    return None

def get_divar(soup, raw):
    raw = html.unescape(raw)

    price = find(
        r'"offers"\s*:\s*\{[^{}]*?"price"\s*:\s*"?(\d+)',
        raw
    )
    km = find(
        r'"mileageFromOdometer"\s*:\s*\{[^{}]*?"value"\s*:\s*"?(\d+)',
        raw
    )
    model = find(r'"model"\s*:\s*"((?:\\.|[^"\\])*)"', raw)
    brand = find(
        r'"brand"\s*:\s*\{[^{}]*?"name"\s*:\s*"((?:\\.|[^"\\])*)"',
        raw
    )
    color = find(r'"color"\s*:\s*"((?:\\.|[^"\\])*)"', raw)
    transmission = find(
        r'"vehicleTransmission"\s*:\s*"([^"]+)"', raw
    )
    city = find(r'"city_persian"\s*:\s*"([^"]+)"', raw)

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    year = None
    match = re.search(r"مدل\s*([۰-۹0-9]{2,4})", digits(title))
    if match:
        y = int(match.group(1))
        if 60 <= y <= 99:
            year = 1300 + y
        elif 1300 <= y <= 1410:
            year = y
        elif 1980 <= y <= 2035:
            year = y

    price = number(price)
    if price is not None:
        price //= 10

    return {
        "site": "دیوار",
        "title": title,
        "brand": brand or model,
        "year": year,
        "km": number(km),
        "price": price,
        "city": city,
        "color": color,
        "gear": transmission,
        "description": "",
        "url": ""
    }

def extract(url):
    if not url.startswith("https://"):
        raise ValueError("لینک باید با https شروع شود")

    if not any(x in url for x in ["divar.ir/", "sheypoor.com/"]):
        raise ValueError("فقط لینک آگهی دیوار یا شیپور پذیرفته می‌شود")

    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    if "sheypoor.com" in url:
        result = get_sheypoor(soup)
    else:
        result = get_divar(soup, r.text)

    if not result:
        raise ValueError("اطلاعات آگهی استخراج نشد")

    result["url"] = result.get("url") or r.url
    result["price"] = result.get("price") or 0
    return result

PAGE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ماشین‌یار</title>
<style>
*{box-sizing:border-box}
body{background:#101827;color:white;font-family:tahoma;margin:0;padding:14px}
main{max-width:650px;margin:auto}
h2{color:#53d9a0;text-align:center}
.box{background:#1d2b40;padding:16px;border-radius:13px;margin:13px 0}
input,button,.btn{width:100%;padding:14px;margin:7px 0;border-radius:8px;font-size:15px}
input{border:1px solid #53657d;background:#101827;color:white}
button,.btn{background:#168c69;color:white;border:0;text-align:center;text-decoration:none;display:block}
.secondary{background:#315477}
.result{background:#173d35;padding:15px;border-radius:10px;line-height:2.1;overflow-wrap:anywhere}
.market{background:#203b50;padding:14px;border-radius:10px;margin-top:12px;line-height:2}
.car{background:#26364b;padding:12px;border-radius:9px;margin:9px 0;line-height:2}
small{color:#bdc9d8}
a{color:#8de5c0}
.price{color:#53d9a0;font-weight:bold}
</style>
</head>
<body>
<main>
<h2>🚘 ماشین‌یار</h2>
<p style="text-align:center">دستیار هوشمند خرید و فروش خودرو</p>

<div class="box">
<form method="POST">
<b>لینک آگهی خودرو را وارد کن:</b>
<input name="url" type="url" placeholder="لینک مستقیم شیپور یا دیوار" required>
<button type="submit">استخراج مشخصات و تحلیل قیمت بازار</button>
</form>
</div>

{% if error %}
<div class="box" style="color:#ffaaaa">{{error}}</div>
{% endif %}

{% if result %}
<div class="box result">
<h3>📋 مشخصات خودرو</h3>
سایت: {{result.site or 'نامشخص'}}<br>
عنوان: {{result.title or 'نامشخص'}}<br>
مدل: {{result.brand or 'نامشخص'}}<br>
سال ساخت: {{result.year or 'نامشخص'}}<br>
کارکرد: {{result.km or 'نامشخص'}} کیلومتر<br>
قیمت فروشنده: <span class="price">{{price}} تومان</span><br>
شهر: {{result.city or 'نامشخص'}}<br>
رنگ: {{result.color or 'نامشخص'}}<br>
گیربکس: {{result.gear or 'نامشخص'}}<br>
توضیحات: {{result.description or 'نامشخص'}}<br>
<a href="{{result.url}}" target="_blank">باز کردن آگهی اصلی</a>
</div>
{% endif %}

{% if market %}
<div class="box market">
<h3>📊 تحلیل قیمت بازار</h3>
تعداد آگهی‌های مشابه معتبر: <b>{{market.comparable_count}}</b><br>
میانه قیمت آگهی‌های مشابه:
<span class="price">{{market_median}} تومان</span><br>
بازه قیمت بازار: {{market_low}}<br>
قیمت پیشنهادی خرید کاسب: {{buy_range}}<br>
بازه فروش مجدد: {{resale_range}}<br>
<hr>
<b>نتیجه بررسی:</b><br>
{{market.assessment or 'نتیجه مشخصی ثبت نشده است'}}
<p><small>{{market.warning or ''}}</small></p>
</div>

{% if comparables %}
<div class="box">
<h3>🚗 آگهی‌های مشابه پیدا شده</h3>
{% for x in comparables %}
<div class="car">
<b>{{x.title or x.model or 'خودروی مشابه'}}</b><br>
سال: {{x.year or 'نامشخص'}} |
کارکرد: {{x.km or 'نامشخص'}}<br>
قیمت آگهی:
<span class="price">{{x.price_fmt}} تومان</span><br>
{% if x.url %}
<a href="{{x.url}}" target="_blank">مشاهده آگهی مشابه</a>
{% endif %}
</div>
{% endfor %}
</div>
{% endif %}
{% endif %}

<div class="box">
<h3>📁 سوابق بررسی</h3>
<a class="btn secondary" href="/history">مشاهده تاریخچه خودروها</a>
</div>
</main>
</body>
</html>
"""

HISTORY = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>سوابق ماشین‌یار</title>
<style>
body{background:#101827;color:white;font-family:tahoma;padding:15px}
.box{background:#1d2b40;padding:14px;border-radius:12px;overflow:auto}
a{color:#70dfb0}
</style>
<h2>📁 سوابق خودروها</h2>
{% for x in cars %}
<div class="box">
<b>{{x.car}}</b> | سال {{x.year or 'نامشخص'}}<br>
کارکرد: {{x.km or 'نامشخص'}}<br>
قیمت آگهی: {{ "{:,}".format(x.price or 0) }} تومان<br>
شهر: {{x.city or 'نامشخص'}}<br>
تاریخ بررسی: {{x.created}}<br>
{% if x.source_url %}<a href="{{x.source_url}}" target="_blank">مشاهده آگهی</a>{% endif %}
</div>
{% else %}
<p>هنوز آگهی‌ای بررسی نشده است.</p>
{% endfor %}
<p><a href="/">بازگشت</a></p>
"""


@app.route("/", methods=["GET", "POST"])
def home():
    result = None
    error = None
    market = None
    price = "0"
    market_median = "نامشخص"
    market_low = "نامشخص"
    buy_range = "نامشخص"
    resale_range = "نامشخص"
    comparables = []

    def money(value):
        try:
            return f"{int(float(value)):,}"
        except (TypeError, ValueError):
            return "نامشخص"

    def show_range(value):
        if isinstance(value, dict):
            low = value.get("low", value.get("min"))
            high = value.get("high", value.get("max"))
            if low is not None and high is not None:
                return money(low) + " تا " + money(high) + " تومان"
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return money(value[0]) + " تا " + money(value[1]) + " تومان"
        if value is not None:
            return money(value) + " تومان"
        return "نامشخص"

    if request.method == "POST":
        url = request.form.get("url", "").strip()
        try:
            if "sheypoor.com" in url:
                from market_engine import analyze_listing

                market = analyze_listing(url)
                v = market.get("vehicle", {})

                result = {
                    "site": "شیپور",
                    "title": v.get("title") or v.get("model"),
                    "brand": v.get("model"),
                    "year": v.get("year"),
                    "km": v.get("km"),
                    "price": v.get("price") or 0,
                    "city": v.get("location"),
                    "color": None,
                    "gear": None,
                    "description": v.get("description"),
                    "url": url
                }

                market_median = money(market.get("market_median"))
                market_low = show_range(
                    [market.get("market_low"), market.get("market_high")]
                    if market.get("market_low") is not None
                    and market.get("market_high") is not None else None
                )
                buy_range = show_range(market.get("dealer_buy_range"))
                resale_range = show_range(market.get("resale_range"))

                raw_comparables = market.get("comparables", [])
                if isinstance(raw_comparables, list):
                    for item in raw_comparables[:15]:
                        if not isinstance(item, dict):
                            continue
                        item = dict(item)
                        item["price_fmt"] = money(item.get("price"))
                        comparables.append(item)

            else:
                result = extract(url)

            price = money(result.get("price"))

            c = db()
            c.execute("""
                INSERT INTO cars
                (car,year,km,city,price,market,value,buy,profit,status,created,
                 source_url,description,color,gear)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                result.get("brand") or result.get("title"),
                str(result.get("year") or ""),
                str(result.get("km") or ""),
                result.get("city") or "",
                result.get("price") or 0,
                market.get("market_median", 0) if market else 0,
                market.get("market_median", 0) if market else 0,
                0, 0,
                "تحلیل قیمت انجام شد" if market else "استخراج مشخصات انجام شد",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                result.get("url"),
                result.get("description"),
                result.get("color"),
                result.get("gear")
            ))
            c.commit()
            c.close()

        except Exception as e:
            error = "خطا در بررسی آگهی: " + str(e)

    return render_template_string(
        PAGE,
        result=result,
        error=error,
        price=price,
        market=market,
        market_median=market_median,
        market_low=market_low,
        buy_range=buy_range,
        resale_range=resale_range,
        comparables=comparables
    )


@app.route("/history")
def history():
    c = db()
    cars = c.execute("SELECT * FROM cars ORDER BY id DESC LIMIT 100").fetchall()
    c.close()
    return render_template_string(HISTORY, cars=cars)



# MARKET_ENGINE_API_ROUTE
@app.route("/api/market-check")
def market_engine_api_route():
    from flask import request, jsonify
    from market_engine import analyze_listing
    link = request.args.get("url", "").strip()
    if not link:
        return jsonify({"error": "لینک آگهی را در پارامتر url وارد کنید"}), 400
    try:
        return jsonify(analyze_listing(link))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
