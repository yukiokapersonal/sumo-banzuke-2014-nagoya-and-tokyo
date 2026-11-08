import sqlite3
import pandas as pd
import streamlit as st
import re

st.set_page_config(
    page_title="大相撲番付表",
    layout="wide"
)

st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Yuji+Boku&display=swap" rel="stylesheet">

    <style>
    /* 全体の上部余白 */
    .block-container { 
        padding-top: 3rem !important; 
        padding-bottom: 4rem; 
        max-width: 100% !important;
    }
    
    h1 {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
        font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    }

    /* 検索バーと番付表の間に十分な距離（余白）を設ける */
    .search-section {
        margin-bottom: 2.5rem;
    }

    /* ページ全体と一体化したテーブルコンテナ */
    .sumo-board {
        width: 100%;
        border: 2px solid #222;
        background: #faf8f5;
        margin-bottom: 2rem;
    }
    
    table.sumo-table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
        table-layout: fixed;
    }
    table.sumo-table th {
        background: #2b2b2b;
        color: #fff;
        padding: 8px 6px;
        position: sticky;
        top: 0;
        z-index: 10;
        font-size: 13px;
        font-weight: normal;
        text-align: left;
    }
    table.sumo-table td {
        padding: 6px 4px;
        border-bottom: 1px solid #e2ded8;
        vertical-align: middle;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    table.sumo-table td.hoshitori-cell {
        text-overflow: clip;
        white-space: nowrap;
    }

    /* 階級ごとの見出しセパレーター */
    tr.division-header-row td {
        background: #3e3a39 !important;
        color: #fffef9 !important;
        font-family: 'Yuji Boku', serif;
        font-size: 16px;
        font-weight: bold;
        letter-spacing: 0.1em;
        padding: 8px 12px;
        border-top: 2px solid #222;
        border-bottom: 2px solid #222;
    }

    .rank-text {
        font-family: 'Yuji Boku', serif;
        font-size: 14px;
        font-weight: bold;
        color: #222;
    }
    .shikona-top-sekitori {
        font-family: 'Yuji Boku', serif;
        font-size: 17px;
        font-weight: 900;
        color: #000;
        letter-spacing: 0.05em;
        margin-right: 6px;
    }
    .shikona-top-toriteki {
        font-family: 'Yuji Boku', serif;
        font-size: 14px;
        font-weight: normal;
        color: #222;
        margin-right: 6px;
    }
    .shikona-bottom {
        font-family: 'Hiragino Mincho ProN', serif;
        font-size: 11px;
        color: #555;
    }
    .meta-text {
        font-size: 12px;
        color: #444;
    }
    
    /* 星取の見切れ防止設定 */
    .hoshitori-text {
        font-family: monospace, serif;
        font-size: 13px;
        letter-spacing: 0px;
        color: #111;
    }

    /* 成績テキスト（通常：負け越し・休場など） */
    .record-text {
        font-weight: bold;
        font-size: 13px;
        color: #111;
        margin-right: 4px;
        display: inline-block;
        padding: 2px 4px;
    }
    
    /* NHK放送風：勝ち越しオレンジハイライト */
    .kachikoshi-orange {
        background-color: #e65100;
        color: #ffffff !important;
        border-radius: 3px;
    }

    /* 三役陣（横綱・大関・関脇・小結）の薄紫ハイライト */
    .sanyaku-bg {
        background-color: #f7f0fa !important;
    }

    /* 金星・配給星のスタイル */
    .star-kinboshi {
        color: #d4af37;
        font-weight: bold;
        font-size: 14px;
    }
    .star-haikyu {
        color: #111111;
        font-weight: bold;
        font-size: 14px;
    }

    /* 表彰バッジ */
    .badge-yusho {
        display: inline-block;
        background-color: #fbc02d;
        color: #111111;
        font-weight: bold;
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 3px;
        margin-right: 2px;
        border: 1px solid #d4af37;
    }
    .badge-jun {
        display: inline-block;
        background-color: #c0c0c0; /* 銀色・シルバー */
        color: #111111;
        font-weight: bold;
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 3px;
        margin-right: 2px;
        border: 1px solid #9e9e9e;
    }
    .badge-shukun {
        display: inline-block;
        background-color: #2e7d32;
        color: #ffffff;
        font-weight: bold;
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 3px;
        margin-right: 2px;
    }
    .badge-kanto {
        display: inline-block;
        background-color: #c62828;
        color: #ffffff;
        font-weight: bold;
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 3px;
        margin-right: 2px;
    }
    .badge-gino {
        display: inline-block;
        background-color: #1565c0;
        color: #ffffff;
        font-weight: bold;
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 3px;
        margin-right: 2px;
    }
    </style>
""", unsafe_allow_html=True)

conn = sqlite3.connect("sumo.db")
cur = conn.cursor()

# 1. 登録されている「場所」の一覧を取得（★ 名古屋と秋場所のみ強制抽出）
cur.execute("SELECT DISTINCT basho_id FROM banzuke WHERE basho_id IN ('201407', '201409') ORDER BY basho_id DESC;")
available_bashos = [r[0] for r in cur.fetchall()]
if not available_bashos: 
    available_bashos = ["201409", "201407"]

# 2. 部屋一覧を取得
TOSHIYORI_LIST = [
    "浅香山", "朝日山", "安治川", "東関", "荒磯", "荒汐", "雷", "伊勢ヶ濱", "伊勢ノ海", "井筒", 
    "稲川", "入間川", "岩友", "浦風", "枝川", "追手風", "阿武松", "大島", "大嶽", "大鳴戸", 
    "大山", "尾車", "押尾川", "音羽山", "尾上", "小野川", "鏡山", "春日野", "春日山", "片男波", 
    "勝ノ浦", "甲山", "北陣", "君ヶ濱", "木瀬（木村瀬平）", "清見潟", "桐山", "熊ヶ谷", "粂川", "九重", 
    "境川", "佐渡ヶ嶽", "佐ノ山", "式秀（式守秀五郎）", "錣山", "芝田山", "白玉", "不知火", "陣幕", "関ノ戸", 
    "千田川", "高崎", "高砂", "高島", "高田川", "武隈", "竹縄", "田子ノ浦", "立田川", "立田山", 
    "立浪", "立川", "楯山", "谷川", "玉垣", "玉ノ井", "千賀ノ浦", "出来山", "出羽海", "時津風", 
    "常盤山", "友綱", "中川", "中立", "中村", "鳴戸", "西岩", "錦島", "錦戸", "二所ノ関", 
    "二十山", "八角", "花籠", "放駒", "浜風", "秀ノ山", "富士ヶ根", "藤島", "二子山", "振分", 
    "間垣", "松ヶ根", "待乳山", "陸奥", "湊", "湊川", "峰崎", "三保ヶ関", "宮城野", "武蔵川", 
    "山科", "山響", "山分", "若藤", "若松"
]

basho_labels = {
    "201407": "平成26年7月場所（名古屋）",
    "201409": "平成26年9月場所（秋場所）"
}

st.markdown('<div class="search-section">', unsafe_allow_html=True)
col1, col2 = st.columns([1, 2])
with col1:
    selected_basho = st.selectbox("場所選択", options=available_bashos, format_func=lambda x: basho_labels.get(x, f"{x[:4]}年{x[4:]}月場所"))
with col2:
    selected_heya = st.selectbox("所属部屋で絞り込み検索", options=["すべて"] + TOSHIYORI_LIST, index=0)
st.markdown('</div>', unsafe_allow_html=True)

st.title(f"大相撲公式番付（{basho_labels.get(selected_basho, selected_basho)}）")

kinboshi_won, kinboshi_lost = {}, {}
tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
if "kinboshi" in tables:
    for day, w_id, l_id in cur.execute("SELECT day, winner_rikishi_id, loser_rikishi_id FROM kinboshi WHERE basho_id=? AND is_fusen=0;", (selected_basho,)).fetchall():
        kinboshi_won.setdefault(w_id, set()).add(day)
        kinboshi_lost.setdefault(l_id, set()).add(day)

cur.execute("PRAGMA table_info(banzuke);")
b_cols = [c[1] for c in cur.fetchall()]
has_hoshi = "hoshitori" in b_cols
has_kettei = "ketteisen" in b_cols
has_yusho = "yusho" in b_cols
has_sansho = "sansho" in b_cols
has_height = "height_cm" in b_cols
has_weight = "weight_kg" in b_cols

cur.execute("PRAGMA table_info(rikishi);")
has_birth = "birth_date" in [c[1] for c in cur.fetchall()]

where_clause = "WHERE b.basho_id = ?"
params = [selected_basho]

if selected_heya != "すべて":
    search_heya = re.sub(r'（.*）', '', selected_heya).strip()
    where_clause += " AND r.heya = ?"
    params.append(search_heya)

query = f"""
WITH RankedBanzuke AS (
    SELECT 
        b.rikishi_id, b.rank_side, b.rank_title, b.rank_number, r.shikona, b.wins,
        IFNULL(r.heya, '-') AS heya, IFNULL(r.shusshin, '-') AS shusshin,
        {"IFNULL(r.birth_date, '-') AS birth_date," if has_birth else "'-' AS birth_date,"}
        {"CASE WHEN b.height_cm IS NOT NULL THEN printf('%g', b.height_cm) || 'cm' ELSE '-' END AS height_str," if has_height else "'-' AS height_str,"}
        {"CASE WHEN b.weight_kg IS NOT NULL THEN printf('%g', b.weight_kg) || 'kg' ELSE '-' END AS weight_str," if has_weight else "'-' AS weight_str,"}
        {"IFNULL(b.hoshitori, '-') AS hoshitori," if has_hoshi else "'-' AS hoshitori,"}
        {"IFNULL(b.ketteisen, '-') AS ketteisen," if has_kettei else "'-' AS ketteisen,"}
        {"IFNULL(b.yusho, '') AS yusho," if has_yusho else "'' AS yusho,"}
        {"IFNULL(b.sansho, '') AS sansho," if has_sansho else "'' AS sansho,"}
        b.rank_division, ROW_NUMBER() OVER (PARTITION BY b.rank_title, b.rank_side ORDER BY r.rikishi_id) as side_order
    FROM banzuke b JOIN rikishi r ON b.rikishi_id = r.rikishi_id {where_clause}
)
SELECT rikishi_id, rank_division, rank_title, wins,
    CASE WHEN rank_number IS NOT NULL AND rank_number = 1 THEN rank_side || rank_title || '筆頭'
         WHEN rank_number IS NOT NULL THEN rank_side || rank_title || rank_number || '枚目'
         WHEN side_order > 1 THEN rank_side || rank_title || side_order || '枚目' ELSE rank_side || rank_title END AS 地位,
    shikona AS 力士名, heya AS 部屋, shusshin AS 出身地, birth_date AS 生年月日, height_str AS 身長, weight_str AS 体重, hoshitori AS 星取, ketteisen AS 決定戦, yusho AS 優勝, sansho AS 三賞
FROM RankedBanzuke
ORDER BY 
    CASE rank_division WHEN '幕内' THEN 1 WHEN '十両' THEN 2 WHEN '幕下' THEN 3 WHEN '三段目' THEN 4 WHEN '序二段' THEN 5 WHEN '序ノ口' THEN 6 ELSE 7 END,
    CASE rank_title WHEN '横綱' THEN 1 WHEN '大関' THEN 2 WHEN '関脇' THEN 3 WHEN '小結' THEN 4 WHEN '前頭' THEN 5 WHEN '十両' THEN 6 WHEN '幕下' THEN 7 WHEN '三段目' THEN 8 WHEN '序二段' THEN 9 WHEN '序ノ口' THEN 10 ELSE 11 END,
    IFNULL(rank_number, side_order) ASC, CASE rank_side WHEN '東' THEN 1 ELSE 2 END
"""

df_table = pd.read_sql_query(query, conn, params=params)
conn.close()

# ----------------------------------------------------
# 各階級ごとに「準優勝」を自動判定
# ----------------------------------------------------
df_table["準優勝"] = ""
if selected_heya == "すべて":
    for div in df_table["rank_division"].unique():
        div_mask = df_table["rank_division"] == div
        champ_df = df_table[div_mask & (df_table["優勝"] == "優")]
        
        if not champ_df.empty:
            champ_wins = champ_df["wins"].max()
            same_wins_mask = div_mask & (df_table["wins"] == champ_wins) & (df_table["優勝"] != "優")
            if same_wins_mask.any():
                df_table.loc[same_wins_mask, "準優勝"] = "準"
            else:
                one_less_mask = div_mask & (df_table["wins"] == champ_wins - 1) & (df_table["優勝"] != "優")
                df_table.loc[one_less_mask, "準優勝"] = "準"

if selected_heya == "すべて":
    st.caption(f"全階級表示中（幕内〜序ノ口・全 {len(df_table)} 名）")
else:
    st.caption(f"「{selected_heya}部屋」の力士を表示中（計 {len(df_table)} 名） ※絞り込み中は準優勝バッジは非表示です")

def split_shikona(name, div):
    if not name: return ""
    parts = name.replace("\u3000", " ").strip().split(" ", 1)
    css_top_class = "shikona-top-sekitori" if div in ["幕内", "十両"] else "shikona-top-toriteki"
    if len(parts) == 2:
        return f'<span class="{css_top_class}">{parts[0]}</span><span class="shikona-bottom">{parts[1]}</span>'
    return f'<span class="{css_top_class}">{parts[0]}</span>'

def render_record_and_awards(yusho, jun_yusho, sansho, hoshitori_str, div):
    rec_str = ""
    if hoshitori_str and hoshitori_str != "-":
        w = hoshitori_str.count('○') + hoshitori_str.count('□')
        l = hoshitori_str.count('●') + hoshitori_str.count('■')
        a = hoshitori_str.count('休') + hoshitori_str.count('や')
        
        if w > 0 or l > 0 or a > 0:
            threshold = 8 if div in ["幕内", "十両"] else 4
            css_class = "record-text kachikoshi-orange" if w >= threshold else "record-text"
            a_str = f"{a}休" if a > 0 else ""
            rec_str = f'<span class="{css_class}">{w}勝{l}敗{a_str}</span>'

    badges = []
    if yusho: badges.append(f'<span class="badge-yusho">{yusho}</span>')
    if jun_yusho: badges.append(f'<span class="badge-jun">{jun_yusho}</span>')
    if sansho:
        for ch in sansho:
            if ch == "殊": badges.append(f'<span class="badge-shukun">殊</span>')
            elif ch == "敢": badges.append(f'<span class="badge-kanto">敢</span>')
            elif ch == "技": badges.append(f'<span class="badge-gino">技</span>')
            else: badges.append(f'<span class="badge-shukun">{ch}</span>')
            
    badges_html = "".join(badges)
    res = ""
    if rec_str: res += rec_str
    if badges_html: res += f" {badges_html}" if res else badges_html
    return res or "-"

def render_hoshitori_html(raw_hoshitori, rid, div):
    if not raw_hoshitori or raw_hoshitori == "-": return "-"
    if div == "幕内" and len(raw_hoshitori) == 15:
        out = []
        won_days = kinboshi_won.get(rid, set())
        lost_days = kinboshi_lost.get(rid, set())
        for idx, mark in enumerate(raw_hoshitori, 1):
            if idx in won_days: out.append('<span class="star-kinboshi">☆</span>')
            elif idx in lost_days: out.append('<span class="star-haikyu">★</span>')
            else: out.append(mark)
        return "".join(out)
    return raw_hoshitori

def convert_to_wareki(date_str):
    if not date_str or date_str == '-': return '-'
    if "昭和" in date_str or "平成" in date_str: return date_str
    m = re.match(r"(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})", date_str)
    if not m: return date_str
    y, m_str, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 1989 or (y == 1989 and (m_str == 1 and d <= 7)):
        return f"昭和{y - 1925}年{m_str}月{d}日"
    else:
        era_str = "元" if y - 1988 == 1 else str(y - 1988)
        return f"平成{era_str}年{m_str}月{d}日"

if len(df_table) == 0:
    st.warning("該当する力士が見つかりませんでした。")
else:
    rows_list = []
    current_div = None

    for _, row in df_table.iterrows():
        div_name = row["rank_division"]
        if div_name != current_div:
            current_div = div_name
            rows_list.append(
                f"<tr class='division-header-row'>"
                f"<td colspan='10'>【 {current_div} 】</td>"
                f"</tr>"
            )

        shikona_html = split_shikona(row["力士名"], row["rank_division"])
        
        jun_val = row["準優勝"] if "準優勝" in row else ""
        record_and_awards_html = render_record_and_awards(row["優勝"], jun_val, row["三賞"], row["星取"], row["rank_division"])
        
        kettei_val = row['決定戦']
        wareki_birth = convert_to_wareki(row['生年月日'])
        hoshi_html = render_hoshitori_html(row['星取'], row['rikishi_id'], row['rank_division'])
        
        is_sanyaku = row["rank_title"] in ["横綱", "大関", "関脇", "小結"]
        row_class = "sanyaku-bg" if is_sanyaku else ""
        
        rows_list.append(
            f"<tr class='{row_class}'>"
            f"<td class='rank-text'>{row['地位']}</td>"
            f"<td>{shikona_html}</td>"
            f"<td class='meta-text'>{row['部屋']}</td>"
            f"<td class='meta-text'>{row['出身地']}</td>"
            f"<td class='meta-text'>{wareki_birth}</td>"
            f"<td class='meta-text'>{row['身長']}</td>"
            f"<td class='meta-text'>{row['体重']}</td>"
            f"<td class='hoshitori-cell hoshitori-text'>{hoshi_html}</td>"
            f"<td class='hoshitori-text' style='text-align:center;'>{kettei_val}</td>"
            f"<td style='text-align:left;'>{record_and_awards_html}</td>"
            f"</tr>"
        )

    table_body = "".join(rows_list)

    table_html = f"""
    <div class="sumo-board">
        <table class="sumo-table">
            <thead>
                <tr>
                    <th style="width: 11%;">地位</th>
                    <th style="width: 14%;">力士名</th>
                    <th style="width: 8%;">部屋</th>
                    <th style="width: 8%;">出身地</th>
                    <th style="width: 10%;">生年月日</th>
                    <th style="width: 5.5%;">身長</th>
                    <th style="width: 5.5%;">体重</th>
                    <th style="width: 21%;">星取</th>
                    <th style="width: 6%; text-align: center;">決定戦</th>
                    <th style="width: 17%; text-align: left;">成績・表彰</th>
                </tr>
            </thead>
            <tbody>
                {table_body}
            </tbody>
        </table>
    </div>
    """

    st.markdown(table_html, unsafe_allow_html=True)