from datetime import datetime
from db.connection import get_connection, USE_POSTGRES, _ph, _rows_to_dicts


def get_github_settings() -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token, github_username, target_repo FROM github_settings WHERE id = 1")
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    if not rows:
        return None
    row = rows[0]
    if not row.get("access_token"):
        return None
    return row


def save_github_settings(access_token: str, github_username: str, target_repo: str = ""):
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()
    now = datetime.now().isoformat()
    if USE_POSTGRES:
        cur.execute(f"""
            INSERT INTO github_settings (id, access_token, github_username, target_repo, updated_at)
            VALUES (1, {p}, {p}, {p}, {p})
            ON CONFLICT (id) DO UPDATE
            SET access_token = EXCLUDED.access_token,
                github_username = EXCLUDED.github_username,
                target_repo = CASE WHEN {p} != '' THEN EXCLUDED.target_repo ELSE github_settings.target_repo END,
                updated_at = EXCLUDED.updated_at
        """, (access_token, github_username, target_repo, now, target_repo))
    else:
        cur.execute(f"""
            INSERT INTO github_settings (id, access_token, github_username, target_repo, updated_at)
            VALUES (1, {p}, {p}, {p}, {p})
            ON CONFLICT(id) DO UPDATE
            SET access_token = excluded.access_token,
                github_username = excluded.github_username,
                target_repo = CASE WHEN {p} != '' THEN excluded.target_repo ELSE github_settings.target_repo END,
                updated_at = excluded.updated_at
        """, (access_token, github_username, target_repo, now, target_repo))
    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def update_github_target_repo(target_repo: str):
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()
    cur.execute(f"UPDATE github_settings SET target_repo = {p} WHERE id = 1", (target_repo,))
    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def delete_github_settings():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM github_settings WHERE id = 1")
    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()
