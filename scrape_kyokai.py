import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time

# ==========================================
# 取得したい場所の設定（ここを変えればどの場所でも取得可能！）
BASHO = "201409"            # 平成26年9月場所
KY_BASHO_ID = "566"         # 協会サイトの場所ID (7月=565, 9月=566)
# ==========================================

BASE_URL = "https://www.sumo.or.jp"
SEARCH_URL = "https://www.sumo.or.jp/ResultRikishiDataDaicho/search/"
TARGET_URL = "https://www.sumo.or.jp/ResultRikishiDataDaicho/banzuke/"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": SEARCH_URL,
    "Origin": BASE_URL,
}

session = requests.Session()
session.get(SEARCH_URL, headers=headers)

DIVISIONS = {1: "幕内", 2: "十両", 3: "幕下", 4: "三段目", 5: "序二段", 6: "序ノ口"}

PREF_PATTERN = r"(北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県|モンゴル|ブルガリア|ジョージア|グルジア|ロシア|ウクライナ|ブラジル|アメリカ|米国|中国|フィリピン|ハンガリー|エジプト|カザフスタン|チェコ|トンガ|サモア|韓国)"
KANJI_VALS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

def kanji_to_num(k_str):
    if not k_str: return None
    if k_str == "筆頭": return 1
    m = re.search(r'\d+', k_str)
    if m: return int(m.group(0))
    total = 0
    if "百" in k_str:
        parts = k_str.split("百")
        total += KANJI_VALS.get(parts[0], 1) * 100
        k_str = parts[1]
    if "十" in k_str:
        parts = k_str.split("十")
        total += KANJI_VALS.get(parts[0], 1) * 10
        k_str = parts[1]
    total += KANJI_VALS.get(k_str, 0)
    return total if total > 0 else None

def parse_name_and_origin(raw_text):
    text = raw_text.replace("\u3000", " ").strip()
    text = re.sub(r'[\(（][^\)）]+[\)）]', '', text).strip()
    m = re.search(PREF_PATTERN, text)
    if m:
        return text[:m.start()].strip(), m.group(1)
    m2 = re.search(r'([一-龥]{2,4}[都道府県])$', text)
    if m2:
        return text[:m2.start()].strip(), m2.group(1)
    return re.sub(r'[a-zA-Z]+$', '', text).strip(), "-"

profile_cache = {}
def fetch_profile_details(profile_url):
    if not profile_url or profile_url in profile_cache:
        return profile_cache.get(profile_url, ("-", "-"))
    heya, birthday = "-", "-"
    try:
        p_res = session.get(profile_url, headers=headers, timeout=4)
        p_soup = BeautifulSoup(p_res.text, "html.parser")
        for th in p_soup.find_all(["th", "td"]):
            t = th.get_text(strip=True)
            if "部屋" in t and heya == "-":
                sib = th.find_next_sibling(["td", "th"])
                if sib: heya = sib.get_text(strip=True).replace("部屋", "")
            if "生年月日" in t and birthday == "-":
                sib = th.find_next_sibling(["td", "th"])
                if sib:
                    b_raw = sib.get_text(strip=True)
                    m = re.search(r'((昭和|平成|\d{4}年)\s*\d+年\s*\d+月\s*\d+日|\d{4}[-/]\d{1,2}[-/]\d{1,2})', b_raw)
                    birthday = m.group(1) if m else b_raw
        profile_cache[profile_url] = (heya, birthday)
        return heya, birthday
    except Exception:
        pass
    return "-", "-"

conn = sqlite3.connect("sumo.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS rikishi (
    rikishi_id INTEGER PRIMARY KEY, shikona TEXT, heya TEXT,
    shusshin TEXT, birth_date TEXT, height REAL, weight REAL, api_rikishi_id INTEGER
);
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS banzuke (
    basho_id TEXT, rikishi_id INTEGER, rank_division TEXT, rank_side TEXT,
    rank_title TEXT, rank_number INTEGER, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, absences INTEGER DEFAULT 0,
    height_cm REAL, weight_kg REAL, measure_basho TEXT, hoshitori TEXT, ketteisen TEXT, yusho TEXT, sansho TEXT,
    PRIMARY KEY (basho_id, rank_division, rank_side, rank_title, rank_number, rikishi_id)
);
""")

# 指定した場所の番付だけをクリーンにして再作成（以前の場所データは消えません）
cur.execute("DELETE FROM banzuke WHERE basho_id = ?;", (BASHO,))

cur.execute("SELECT IFNULL(MAX(rikishi_id), 0) FROM rikishi;")
max_id = cur.fetchone()[0]
rikishi_seq = max_id + 1

INVALID_WORDS = ["東", "西", "番付", "<<<", ">>>", "<<", ">>", "<", ">", "前へ", "次へ"]
total_count = 0

print(f"【{BASHO} 取得中】全階級の番付を取得しています...")

for kakuzuke_id, div_name in DIVISIONS.items():
    page = 1
    div_count = 0
    while True:
        payload = {"basho_id": KY_BASHO_ID, "kakuzuke": str(kakuzuke_id), "page": str(page)}
        try:
            res = session.post(TARGET_URL, data=payload, headers=headers, timeout=8)
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, "html.parser")
        except Exception:
            break

        tables = soup.find_all("table")
        if not tables: break

        page_saved = 0
        for table in tables:
            for row in table.find_all("tr"):
                cols = row.find_all(["th", "td"])
                if len(cols) != 3: continue
                east_raw, rank_raw, west_raw = cols[0].get_text(strip=True), cols[1].get_text(strip=True), cols[2].get_text(strip=True)

                if any(w in rank_raw for w in ["番付", "東", "西", "<", ">"]) or not rank_raw: continue
                if east_raw in INVALID_WORDS or west_raw in INVALID_WORDS: continue

                if rank_raw in ["横綱", "大関", "関脇", "小結"]:
                    rank_title = rank_raw
                    rank_number = None
                else:
                    rank_title = "前頭" if ("前頭" in rank_raw or rank_raw.startswith("前")) else div_name
                    pure_num = re.sub(r'^(幕内|十両|幕下|三段目|序二段|序ノ口|前頭|前)', '', rank_raw).replace("枚目", "").strip()
                    rank_number = kanji_to_num(pure_num)

                e_url = (BASE_URL + cols[0].find("a")["href"]) if cols[0].find("a") else None
                w_url = (BASE_URL + cols[2].find("a")["href"]) if cols[2].find("a") else None

                for side, raw_name, p_url in [("東", east_raw, e_url), ("西", west_raw, w_url)]:
                    if not raw_name or raw_name in INVALID_WORDS or "<" in raw_name: continue
                    shikona, origin = parse_name_and_origin(raw_name)
                    if not shikona: continue

                    heya, birthday = fetch_profile_details(p_url) if p_url else ("-", "-")
                    cur.execute("SELECT rikishi_id FROM rikishi WHERE shikona = ?;", (shikona,))
                    r_row = cur.fetchone()
                    if r_row:
                        r_id = r_row[0]
                        cur.execute("UPDATE rikishi SET heya=CASE WHEN ?!='-' THEN ? ELSE heya END, shusshin=CASE WHEN ?!='-' THEN ? ELSE shusshin END, birth_date=CASE WHEN ?!='-' THEN ? ELSE birth_date END WHERE rikishi_id=?;", (heya, heya, origin, origin, birthday, birthday, r_id))
                    else:
                        r_id = rikishi_seq
                        rikishi_seq += 1
                        cur.execute("INSERT OR REPLACE INTO rikishi (rikishi_id, shikona, heya, shusshin, birth_date) VALUES (?, ?, ?, ?, ?);", (r_id, shikona, heya, origin, birthday))

                    cur.execute("""
                        INSERT OR REPLACE INTO banzuke 
                        (basho_id, rikishi_id, rank_division, rank_side, rank_title, rank_number, wins, losses, absences)
                        VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0);
                    """, (BASHO, r_id, div_name, side, rank_title, rank_number))

                    page_saved += 1
                    div_count += 1
                    total_count += 1

        if page_saved == 0: break
        if kakuzuke_id in [1, 2]: break
        if not any(f"banzuke({KY_BASHO_ID},{kakuzuke_id},{page+1})" in str(soup) for _ in [1]): break
        page += 1
        time.sleep(0.2)

    print(f"  ✔ 【{div_name}】完了（{div_count} 名）")
    conn.commit()

conn.close()
print(f"\n{BASHO} の番付データ {total_count} 名が追加されました！")