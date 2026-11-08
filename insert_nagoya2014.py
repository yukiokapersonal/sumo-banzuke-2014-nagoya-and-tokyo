import sqlite3

conn = sqlite3.connect("sumo.db")
cur = conn.cursor()

# 1. 場所マスタに「2014年7月場所」を登録
cur.execute(
    """
INSERT OR IGNORE INTO basho (basho_id, year, month, location)
VALUES ('201407', 2014, 7, '愛知県体育館（名古屋）');
"""
)

# 2. 力士マスタの登録（平成26年名古屋場所の主な上位力士）
rikishi_data = [
    (1, "白鵬 翔", "宮城野", "モンゴル・ウランバートル"),
    (2, "日馬富士 公平", "伊勢ヶ濱", "モンゴル・ゴビアルタイ"),
    (3, "鶴竜 力三郎", "井筒", "モンゴル・スフバートル"),
    (4, "稀勢の里 寛", "田子ノ浦", "茨城県牛久市"),
    (5, "琴奨菊 一弘", "佐渡ヶ嶽", "福岡県柳川市"),
    (6, "豪栄道 豪太郎", "境川", "大阪府寝屋川市"),
    (7, "栃煌山 雄一郎", "春日野", "高知県安芸市"),
    (8, "碧山 亘", "春日野", "ブルガリア・ヤンボル"),
    (9, "照ノ富士 春雄", "伊勢ヶ濱", "モンゴル・ウランバートル"),
    (10, "遠藤 聖大", "追手風", "石川県鳳珠郡"),
]

cur.executemany(
    """
INSERT OR IGNORE INTO rikishi (rikishi_id, shikona, heya, shusshin)
VALUES (?, ?, ?, ?);
""",
    rikishi_data,
)

# 3. 番付・成績データの登録（平成26年名古屋場所）
# (basho_id, rikishi_id, rank_division, rank_side, rank_title, rank_number, wins, losses, absences)
banzuke_data = [
    ("201407", 1, "幕内", "東", "横綱", None, 13, 2, 0),  # 白鵬（優勝）
    ("201407", 2, "幕内", "西", "横綱", None, 10, 5, 0),  # 日馬富士
    ("201407", 3, "幕内", "東", "横綱2", None, 11, 4, 0),  # 鶴竜
    ("201407", 4, "幕内", "東", "大関", 1, 9, 6, 0),  # 稀勢の里
    ("201407", 5, "幕内", "西", "大関", 1, 9, 6, 0),  # 琴奨菊
    (
        "201407",
        6,
        "幕内",
        "東",
        "関脇",
        1,
        12,
        3,
        0,
    ),  # 豪栄道（技能賞・場所後大関昇進）
    ("201407", 7, "幕内", "西", "関脇", 1, 2, 13, 0),  # 栃煌山
    ("201407", 8, "幕内", "東", "小結", 1, 6, 9, 0),  # 碧山
    ("201407", 9, "幕内", "東", "前頭", 6, 9, 6, 0),  # 照ノ富士
    ("201407", 10, "幕内", "西", "前頭", 1, 9, 6, 0),  # 遠藤
]

cur.executemany(
    """
INSERT OR REPLACE INTO banzuke 
(basho_id, rikishi_id, rank_division, rank_side, rank_title, rank_number, wins, losses, absences)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
    banzuke_data,
)

conn.commit()
conn.close()
print("平成26年名古屋場所のデータを登録しました！")