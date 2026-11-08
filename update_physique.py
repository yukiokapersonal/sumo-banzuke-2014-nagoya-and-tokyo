import os
import re
import json
import time
import sqlite3
import requests
from bs4 import BeautifulSoup

# ==========================================
# 取得対象の場所設定（ここを変えるだけでどの場所でもOK！）
BASHO = "201409"            # 平成26年9月場所（秋場所）
KY_BASHO_ID = "566"         # 協会サイト側の場所ID（7月=565, 9月=566, 11月=567）
# ==========================================

# キャッシュディレクトリの準備
CACHE_DIR = "api_cache"
PROFILE_CACHE_DIR = os.path.join(CACHE_DIR, "profiles")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(PROFILE_CACHE_DIR, exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_json(url, cache_filename):
    cache_path = os.path.join(CACHE_DIR, cache_filename)
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            time.sleep(0.1)
            return data
    except Exception as e:
        print(f"! API通信エラー ({url}): {e}")
    return None

conn = sqlite3.connect("sumo.db")
cur = conn.cursor()

print("=================================================================")
print(f"【準備】データベース確認中（対象場所: {BASHO}）...")
print("=================================================================")

cur.execute("PRAGMA table_info(banzuke);")
banzuke_cols = [c[1] for c in cur.fetchall()]
for col, col_type in [("height_cm", "REAL"), ("weight_kg", "REAL"), ("measure_basho", "TEXT")]:
    if col not in banzuke_cols:
        cur.execute(f"ALTER TABLE banzuke ADD COLUMN {col} {col_type};")

cur.execute("PRAGMA table_info(rikishi);")
rikishi_cols = [c[1] for c in cur.fetchall()]
for col, col_type in [("height", "REAL"), ("weight", "REAL"), ("api_rikishi_id", "INTEGER")]:
    if col not in rikishi_cols:
        cur.execute(f"ALTER TABLE rikishi ADD COLUMN {col} {col_type};")
conn.commit()


# ==============================================================================
# STEP 1: 関取（幕内・十両）のデータをSumo APIから取得＆反映
# ==============================================================================
print(f"\n【STEP 1】関取（幕内・十両）の地位突合および体格データ取得中...")

cur.execute("""
    SELECT b.rikishi_id, b.rank_division, b.rank_side, b.rank_title, b.rank_number
    FROM banzuke b
    WHERE b.basho_id = ? AND b.rank_division IN ('幕内', '十両')
    ORDER BY 
        CASE b.rank_division WHEN '幕内' THEN 1 ELSE 2 END,
        CASE b.rank_title
            WHEN '横綱' THEN 1 WHEN '大関' THEN 2 WHEN '関脇' THEN 3
            WHEN '小結' THEN 4 WHEN '前頭' THEN 5 WHEN '十両' THEN 6
        END,
        IFNULL(b.rank_number, 0),
        b.rikishi_id;
""", (BASHO,))
db_rows = cur.fetchall()

db_grouped = {}
for r_id, div, side, title, num in db_rows:
    key = (div, side, title)
    if key not in db_grouped:
        db_grouped[key] = []
    num_val = int(num) if num is not None else 0
    db_grouped[key].append((r_id, num_val))

matched_rikishi = []
DIV_CONFIG = [("Makuuchi", "幕内"), ("Juryo", "十両")]

for div_en, div_jp in DIV_CONFIG:
    banzuke_url = f"https://sumo-api.com/api/basho/{BASHO}/banzuke/{div_en}"
    data = get_json(banzuke_url, f"banzuke_{BASHO}_{div_en}.json")
    if not data:
        continue

    for side_key, side_jp in [("east", "東"), ("west", "西")]:
        entries = data.get(side_key, [])
        api_grouped = {}
        for entry in entries:
            raw_rank = entry.get("rank", "")
            if "Yokozuna" in raw_rank: t = "横綱"
            elif "Ozeki" in raw_rank: t = "大関"
            elif "Sekiwake" in raw_rank: t = "関脇"
            elif "Komusubi" in raw_rank: t = "小結"
            elif "Maegashira" in raw_rank: t = "前頭"
            else: t = "十両"

            num_val = 0
            for part in raw_rank.split():
                if part.isdigit():
                    num_val = int(part)
                    break

            if t not in api_grouped:
                api_grouped[t] = []
            api_grouped[t].append((entry, num_val))

        for t, api_list in api_grouped.items():
            db_list = db_grouped.get((div_jp, side_jp, t), [])
            if t in ["前頭", "十両"]:
                for entry, api_num in api_list:
                    api_id = entry.get("rikishiID")
                    shikona_en = entry.get("shikonaEn", "")
                    for db_id, db_num in db_list:
                        if db_num == api_num:
                            matched_rikishi.append((db_id, api_id, shikona_en, entry))
                            break
            else:
                for idx, (entry, _) in enumerate(api_list):
                    api_id = entry.get("rikishiID")
                    shikona_en = entry.get("shikonaEn", "")
                    if idx < len(db_list):
                        db_id = db_list[idx][0]
                        matched_rikishi.append((db_id, api_id, shikona_en, entry))

sekitori_updated = 0
exact_basho_count = 0

for db_id, api_id, shikona_en, banzuke_entry in matched_rikishi:
    cur.execute("UPDATE rikishi SET api_rikishi_id = ? WHERE rikishi_id = ?", (api_id, db_id))

    m_url = f"https://sumo-api.com/api/measurements?rikishiId={api_id}"
    m_data = get_json(m_url, f"meas_{api_id}.json")

    records = []
    if isinstance(m_data, list):
        records = m_data
    elif isinstance(m_data, dict):
        records = m_data.get("records", m_data.get("measurements", []))

    h_val, w_val, target_basho = None, None, None

    valid_records = [
        r for r in records 
        if r.get("height") and r.get("weight") and str(r.get("bashoId") or r.get("basho") or "") <= BASHO
    ]
    valid_records.sort(key=lambda x: str(x.get("bashoId") or x.get("basho") or ""), reverse=True)

    if valid_records:
        latest = valid_records[0]
        h_val = float(latest.get("height"))
        w_val = float(latest.get("weight"))
        target_basho = str(latest.get("bashoId") or latest.get("basho") or "")
        if BASHO in target_basho:
            exact_basho_count += 1

    if not h_val:
        if banzuke_entry.get("height") and banzuke_entry.get("weight"):
            h_val = float(banzuke_entry.get("height"))
            w_val = float(banzuke_entry.get("weight"))
            target_basho = f"{BASHO}(番付)"
        else:
            r_url = f"https://sumo-api.com/api/rikishi/{api_id}"
            r_data = get_json(r_url, f"rikishi_{api_id}.json")
            if r_data and r_data.get("height") and r_data.get("weight"):
                h_val = float(r_data.get("height"))
                w_val = float(r_data.get("weight"))
                target_basho = "公称値"

    if h_val and w_val:
        cur.execute("""
            UPDATE banzuke 
            SET height_cm = ?, weight_kg = ?, measure_basho = ?
            WHERE basho_id = ? AND rikishi_id = ?
        """, (h_val, w_val, target_basho, BASHO, db_id))
        cur.execute("""
            UPDATE rikishi 
            SET height = ?, weight = ?
            WHERE rikishi_id = ?
        """, (h_val, w_val, db_id))
        sekitori_updated += 1

conn.commit()
print(f"  ✔ 関取 {sekitori_updated}/70 名の体格データを反映完了（うち{BASHO}直近実測: {exact_basho_count} 名）")


# ==============================================================================
# STEP 2: 取的（幕下以下）の体格データを日本相撲協会・番付台帳リンクからスクレイピング
# ==============================================================================
print(f"\n【STEP 2】取的（幕下〜序ノ口）のデータを番付台帳からスクレイピング中...")

BASE_URL = "https://www.sumo.or.jp"
SEARCH_URL = "https://www.sumo.or.jp/ResultRikishiDataDaicho/search/"
TARGET_URL = "https://www.sumo.or.jp/ResultRikishiDataDaicho/banzuke/"

session = requests.Session()
session.get(SEARCH_URL, headers=headers)

TORITEKI_DIVS = {3: "幕下", 4: "三段目", 5: "序二段", 6: "序ノ口"}
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

def fetch_daicho_physique(profile_url):
    if not profile_url:
        return None, None
    prof_id = profile_url.rstrip("/").split("/")[-1]
    cache_file = os.path.join(PROFILE_CACHE_DIR, f"prof_{prof_id}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d.get("h"), d.get("w")

    try:
        res = session.get(profile_url, headers=headers, timeout=6)
        res.encoding = res.apparent_encoding
        text = BeautifulSoup(res.text, "html.parser").get_text()
        h_m = re.search(r"(\d{3}(?:\.\d)?)\s*cm", text)
        w_m = re.search(r"(\d{2,3}(?:\.\d)?)\s*kg", text)
        h = float(h_m.group(1)) if h_m else None
        w = float(w_m.group(1)) if w_m else None
        if h and w:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"h": h, "w": w}, f)
        time.sleep(0.05)
        return h, w
    except:
        return None, None

daicho_updated = 0
for kakuzuke_id, div_name in TORITEKI_DIVS.items():
    page = 1
    div_updated = 0
    while True:
        payload = {"basho_id": KY_BASHO_ID, "kakuzuke": str(kakuzuke_id), "page": str(page)}
        try:
            res = session.post(TARGET_URL, data=payload, headers=headers, timeout=8)
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, "html.parser")
        except:
            break

        tables = soup.find_all("table")
        if not tables:
            break

        page_found = 0
        for table in tables:
            for row in table.find_all("tr"):
                cols = row.find_all(["th", "td"])
                if len(cols) != 3:
                    continue
                rank_raw = cols[1].get_text(strip=True)
                if not rank_raw or any(w in rank_raw for w in ["番付", "東", "西", "<", ">"]):
                    continue

                pure_num = re.sub(r'^(幕下|三段目|序二段|序ノ口)', '', rank_raw).replace("枚目", "").strip()
                rank_number = kanji_to_num(pure_num)

                for side_jp, col in [("東", cols[0]), ("西", cols[2])]:
                    raw_name = col.get_text(strip=True)
                    if not raw_name or "<" in raw_name:
                        continue
                    page_found += 1

                    a_tag = col.find("a", href=True)
                    if not a_tag:
                        continue
                    p_url = BASE_URL + a_tag["href"] if a_tag["href"].startswith("/") else a_tag["href"]

                    cur.execute("""
                        SELECT b.rikishi_id, b.height_cm 
                        FROM banzuke b
                        WHERE b.basho_id = ? AND b.rank_division = ? AND b.rank_side = ? AND b.rank_number = ?
                    """, (BASHO, div_name, side_jp, rank_number))
                    target_row = cur.fetchone()

                    if target_row and target_row[1] is None:
                        r_id = target_row[0]
                        h, w = fetch_daicho_physique(p_url)
                        if h and w:
                            cur.execute("""
                                UPDATE banzuke SET height_cm = ?, weight_kg = ?, measure_basho = '協会台帳'
                                WHERE basho_id = ? AND rikishi_id = ?
                            """, (h, w, BASHO, r_id))
                            cur.execute("""
                                UPDATE rikishi SET height = ?, weight = ?
                                WHERE rikishi_id = ?
                            """, (h, w, r_id))
                            daicho_updated += 1
                            div_updated += 1

        if page_found == 0 or f"banzuke({KY_BASHO_ID},{kakuzuke_id},{page+1})" not in str(soup):
            break
        page += 1
    conn.commit()
    print(f"  ✔ 【{div_name}】台帳からの体格反映: {div_updated} 名")


# ==============================================================================
# STEP 3: 台帳リンクが無く身長・体重が抜けている取的力士を協会検索で自動補完
# ==============================================================================
print(f"\n【STEP 3】取的の欠損データをチェックし、抜けている力士を自動補完中...")

cur.execute("""
    SELECT DISTINCT b.rikishi_id, r.shikona, b.rank_division
    FROM banzuke b
    JOIN rikishi r ON b.rikishi_id = r.rikishi_id
    WHERE b.basho_id = ? AND b.height_cm IS NULL
    ORDER BY b.rikishi_id;
""", (BASHO,))
missing_targets = cur.fetchall()

if not missing_targets:
    print("  ✔ 欠損している力士は0名です！全員分のデータが入っています。")
else:
    print(f"  → 未登録の力士が {len(missing_targets)} 名見つかりました。検索補完を実行します...")
    BASE_SEARCH_URL = "https://www.sumo.or.jp/ResultRikishiData/search/"
    toriteki_fixed = 0

    for db_id, raw_shikona, div_name in missing_targets:
        main_shikona = raw_shikona.split()[0].replace("\u3000", "").strip()
        try:
            search_res = requests.post(BASE_SEARCH_URL, data={"shikona": main_shikona}, headers=headers, timeout=8)
            if search_res.status_code != 200:
                continue

            soup = BeautifulSoup(search_res.text, "html.parser")
            prof_link = None
            for a in soup.find_all("a", href=True):
                if "/ResultRikishiData/profile/" in a["href"]:
                    prof_link = a["href"]
                    break

            if not prof_link:
                continue

            full_prof_url = "https://www.sumo.or.jp" + prof_link if prof_link.startswith("/") else prof_link
            prof_res = requests.get(full_prof_url, headers=headers, timeout=8)
            if prof_res.status_code != 200:
                continue

            page_text = BeautifulSoup(prof_res.text, "html.parser").get_text()
            h_match = re.search(r"(\d{3}(?:\.\d)?)\s*cm", page_text)
            w_match = re.search(r"(\d{2,3}(?:\.\d)?)\s*kg", page_text)

            if h_match and w_match:
                h = float(h_match.group(1))
                w = float(w_match.group(1))

                cur.execute("""
                    UPDATE banzuke SET height_cm = ?, weight_kg = ?, measure_basho = '協会検索補完'
                    WHERE basho_id = ? AND rikishi_id = ?
                """, (h, w, BASHO, db_id))
                cur.execute("""
                    UPDATE rikishi SET height = ?, weight = ?
                    WHERE rikishi_id = ?
                """, (h, w, db_id))
                toriteki_fixed += 1
                print(f"    ・補完成功: {raw_shikona} ({div_name}) -> {h}cm / {w}kg")
            time.sleep(0.2)
        except:
            continue

    conn.commit()
    print(f"  ✔ 欠損していた {toriteki_fixed} 名のデータを検索補完しました！")


# ==============================================================================
# STEP 4: 最終確認レポート
# ==============================================================================
print("\n=================================================================")
print(f"【STEP 4】{BASHO} 身長・体重 最終確認レポート")
print("=================================================================")

cur.execute("""
    SELECT 
        rank_division,
        COUNT(*) AS total,
        COUNT(height_cm) AS filled,
        COUNT(*) - COUNT(height_cm) AS missing
    FROM banzuke
    WHERE basho_id = ?
    GROUP BY rank_division
    ORDER BY CASE rank_division
        WHEN '幕内' THEN 1 WHEN '十両' THEN 2 WHEN '幕下' THEN 3
        WHEN '三段目' THEN 4 WHEN '序二段' THEN 5 WHEN '序ノ口' THEN 6
    END;
""", (BASHO,))
summary_rows = cur.fetchall()

for div, total, filled, missing in summary_rows:
    status = "OK (完全一致)" if missing == 0 else f"残り未取得 {missing}名"
    print(f"  ・{div:<4}: 全 {total:>3} 名 | 登録済 {filled:>3} 名 | {status}")

conn.close()
print("\nすべての体格処理が完了しました！")