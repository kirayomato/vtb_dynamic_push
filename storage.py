"""持久化存储模块

基于 SQLite 的本地状态存储，解决程序重启后所有内存状态丢失、
必须重新从头初始化的问题，同时支持离线查询历史数据。

- kv 表: 存储 uid -> 任意JSON值 的键值状态（昵称/头像/签名/直播状态/计数等）
- dynamics 表: 存储各平台的动态/微博/文章 (platform, uid, item_id, content, pic_url, ts)

线程安全（RLock + WAL 模式），所有写入失败仅记录日志，不影响查询主流程。
"""

import atexit
import json
import os
import sqlite3
import threading
from datetime import datetime

prefix = "【持久化存储】"

#: 重启恢复时每个 uid 最多还原多少条动态，避免长期运行后把历史全量灌进内存
RESTORE_LIMIT = 50

_conn = None
_lock = threading.RLock()


def _log(level: str, msg: str) -> None:
    """惰性载入项目 logger，避免 import storage 时连带拉起 web 服务依赖。

    日志在拿锁之外调用，规避持锁调用外部组件的死锁风险。
    """
    try:
        from logger import logger

        getattr(logger, level)(msg, prefix)
    except Exception:
        print(f"{prefix} {msg}")


def _db_path() -> str:
    """数据库固定落在项目根目录下的 data/，不随进程工作目录漂移。"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "state.db"
    )


def _get_conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        path = _db_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("""CREATE TABLE IF NOT EXISTS kv (
                store TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (store, key)
            )""")
        _conn.execute("""CREATE TABLE IF NOT EXISTS dynamics (
                platform TEXT NOT NULL,
                uid TEXT NOT NULL,
                item_id TEXT NOT NULL,
                content TEXT,
                pic_url TEXT,
                ts REAL,
                deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at REAL,
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (platform, uid, item_id)
            )""")
        _conn.execute("""CREATE TABLE IF NOT EXISTS kv_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                changed_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            )""")
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dynamics_lookup "
            "ON dynamics (platform, uid, ts)"
        )
        # 旧版本库迁移：dynamics 补充软删除列
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(dynamics)")]
        if "deleted" not in cols:
            _conn.execute(
                "ALTER TABLE dynamics ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0"
            )
        if "deleted_at" not in cols:
            _conn.execute("ALTER TABLE dynamics ADD COLUMN deleted_at REAL")
        _conn.commit()
    _log("info", f"持久化存储已连接: {path}")
    return _conn


def close() -> None:
    """关闭连接前把 WAL 落盘，保证直接拷贝 state.db 也是完整数据。"""
    global _conn
    with _lock:
        if _conn is None:
            return
        try:
            _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            _conn.commit()
        except Exception as e:
            _log("error", f"关闭前落盘失败: {e}")
        try:
            _conn.close()
        except Exception as e:
            _log("error", f"关闭数据库连接失败: {e}")
        _conn = None


atexit.register(close)


# ---------------- kv 键值状态 ----------------


def kv_set(store: str, key, value) -> None:
    """写入/更新一条键值状态（value 需可JSON序列化，None 也会原样存储）。

    值未发生变化时直接返回，不写 kv 表也不写历史。WAL 模式下每次 commit
    都会向 WAL 追加整页，轮询场景里无脑重写会带来数百倍的写入放大。
    值发生变化时，另外在 kv_history 表追加一条历史记录。
    """
    try:
        conn = _get_conn()
        payload = json.dumps(value, ensure_ascii=False)
        with _lock:
            old = conn.execute(
                "SELECT value FROM kv WHERE store = ? AND key = ?",
                (store, str(key)),
            ).fetchone()
            if old is None:
                changed = True
            else:
                try:
                    changed = (
                        json.loads(old[0]) != value
                        if old[0] is not None
                        else value is not None
                    )
                except (ValueError, TypeError):
                    changed = True
            if not changed:
                return
            conn.execute(
                "INSERT INTO kv_history (store, key, value, changed_at) "
                "VALUES (?, ?, ?, strftime('%s','now'))",
                (store, str(key), payload),
            )
            conn.execute(
                "INSERT OR REPLACE INTO kv (store, key, value, updated_at) "
                "VALUES (?, ?, ?, strftime('%s','now'))",
                (store, str(key), payload),
            )
            conn.commit()
    except Exception as e:
        _log("error", f"写入状态失败 store={store} key={key}: {e}")


def kv_del(store: str, key) -> None:
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "DELETE FROM kv WHERE store = ? AND key = ?", (store, str(key))
            )
            conn.commit()
    except Exception as e:
        _log("error", f"删除状态失败 store={store} key={key}: {e}")


def kv_load(store: str) -> dict:
    """加载某个 store 下的全部键值状态, 返回 {key: value}"""
    try:
        conn = _get_conn()
        with _lock:
            rows = conn.execute(
                "SELECT key, value FROM kv WHERE store = ?", (store,)
            ).fetchall()
        return {k: json.loads(v) if v is not None else None for k, v in rows}
    except Exception as e:
        _log("error", f"加载状态失败 store={store}: {e}")
        return {}


def kv_history(store: str, key=None, limit: int = 500) -> list:
    """查询某 store 的历史变更记录，按时间倒序。

    返回 [{key, value, changed_at}]；指定 key 时只查该键。
    """
    try:
        conn = _get_conn()
        with _lock:
            if key is None:
                rows = conn.execute(
                    "SELECT key, value, changed_at FROM kv_history WHERE store = ? "
                    "ORDER BY changed_at DESC, id DESC LIMIT ?",
                    (store, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key, value, changed_at FROM kv_history "
                    "WHERE store = ? AND key = ? "
                    "ORDER BY changed_at DESC, id DESC LIMIT ?",
                    (store, str(key), limit),
                ).fetchall()
        return [
            {
                "key": k,
                "value": json.loads(v) if v is not None else None,
                "changed_at": c,
            }
            for k, v, c in rows
        ]
    except Exception as e:
        _log("error", f"查询历史失败 store={store}: {e}")
        return []


# ---------------- dynamics 动态数据 ----------------


_DYN_UPSERT_SQL = (
    "INSERT INTO dynamics "
    "(platform, uid, item_id, content, pic_url, ts, deleted, deleted_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, 0, NULL, strftime('%s','now')) "
    "ON CONFLICT(platform, uid, item_id) DO UPDATE SET "
    "content = excluded.content, pic_url = excluded.pic_url, "
    "ts = excluded.ts, deleted = 0, deleted_at = NULL, "
    "updated_at = excluded.updated_at"
)


def _pack_pic(pic_url):
    """pic_url 可能是 str / list / None，统一序列化后再入库。"""
    return json.dumps(pic_url, ensure_ascii=False) if pic_url is not None else None


def _coerce_ts(ts):
    """把所有来源的 ts 统一规范化为数值，避免非数值类型污染数据库。

    接受 int/float、datetime 对象（转 .timestamp()）、以及历史脏数据中可能是
    ISO 字符串的 ts；无法解析时返回 0.0，保证 get_active 等比较逻辑不会
    因类型不匹配而抛异常。
    """
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, datetime):
        return ts.timestamp()
    if isinstance(ts, str):
        s = ts.strip()
        try:
            return float(s)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    try:
        return float(ts)
    except (TypeError, ValueError):
        return 0.0


def dyn_set(platform: str, uid, item_id, content, pic_url, ts) -> None:
    """写入/更新一条动态记录。pic_url 可为 str/list/None。

    若该记录此前被标记删除（软删除），重新写入时自动恢复为未删除。
    """
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                _DYN_UPSERT_SQL,
                (
                    platform,
                    str(uid),
                    str(item_id),
                    content,
                    _pack_pic(pic_url),
                    _coerce_ts(ts),
                ),
            )
            conn.commit()
    except Exception as e:
        _log(
            "error",
            f"写入动态失败 platform={platform} uid={uid} id={item_id}: {e}",
        )


def dyn_set_many(platform: str, uid, items: dict) -> None:
    """单事务批量写入同一 uid 的多条动态，供初始化等成批写入场景使用。

    items 形如 {item_id: (content, pic_url, ts)}。相比循环调用 dyn_set，
    这里只提交一次事务，避免 N 次 commit 带来的 WAL 写入放大。
    """
    if not items:
        return
    try:
        conn = _get_conn()
        rows = [
            (
                platform,
                str(uid),
                str(item_id),
                content,
                _pack_pic(pic_url),
                _coerce_ts(ts),
            )
            for item_id, (content, pic_url, ts) in items.items()
        ]
        with _lock:
            conn.executemany(_DYN_UPSERT_SQL, rows)
            conn.commit()
    except Exception as e:
        _log(
            "error",
            f"批量写入动态失败 platform={platform} uid={uid} 共{len(items)}条: {e}",
        )


def dyn_del(platform: str, uid, item_id) -> None:
    """软删除：仅打删除标记，不物理移除，保留历史可离线查询。"""
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "UPDATE dynamics SET deleted = 1, deleted_at = strftime('%s','now'), "
                "updated_at = strftime('%s','now') "
                "WHERE platform = ? AND uid = ? AND item_id = ? AND deleted = 0",
                (platform, str(uid), str(item_id)),
            )
            conn.commit()
    except Exception as e:
        _log("error", f"删除动态失败 platform={platform} uid={uid} id={item_id}: {e}")


_DYN_LOAD_SQL = (
    "SELECT uid, item_id, content, pic_url, ts FROM ("
    " SELECT uid, item_id, content, pic_url, ts,"
    " ROW_NUMBER() OVER (PARTITION BY uid ORDER BY COALESCE(ts, 0) DESC) AS rn"
    " FROM dynamics WHERE platform = ?{uid_filter} AND deleted = 0"
    ") WHERE rn <= ?"
)


def dyn_load(platform: str, uid=None, limit: int = RESTORE_LIMIT) -> dict:
    """加载未删除的动态数据（用于重启恢复内存状态）。

    返回 {uid: {item_id: (content, pic_url, ts)}}；指定 uid 时只返回该用户。
    每个 uid 默认只还原最近 limit 条（按 ts 倒序），避免长期运行后重启时把
    历史全量灌进内存。已软删除的记录不返回。pic_url 反序列化回 str/list。
    """
    limit = RESTORE_LIMIT if limit is None else limit
    try:
        conn = _get_conn()
        if uid is None:
            sql = _DYN_LOAD_SQL.format(uid_filter="")
            params: tuple = (platform, limit)
        else:
            sql = _DYN_LOAD_SQL.format(uid_filter=" AND uid = ?")
            params = (platform, str(uid), limit)
        with _lock:
            rows = conn.execute(sql, params).fetchall()
        result: dict = {}
        for _uid, item_id, content, pic, ts in rows:
            result.setdefault(_uid, {})[item_id] = (
                content,
                json.loads(pic) if pic is not None else None,
                _coerce_ts(ts),
            )
        return result
    except Exception as e:
        _log("error", f"加载动态失败 platform={platform}: {e}")
        return {}


def dyn_query(
    platform: str, uid=None, include_deleted: bool = False, limit: int = None
) -> list:
    """平铺查询动态记录（供离线查询接口使用），按 ts 倒序。

    返回 [{uid, id, content, pic_url, ts, deleted, deleted_at}]；
    include_deleted=True 时包含已软删除的历史记录。
    """
    try:
        sql = (
            "SELECT uid, item_id, content, pic_url, ts, deleted, deleted_at "
            "FROM dynamics WHERE platform = ?"
        )
        params = [platform]
        if uid is not None:
            sql += " AND uid = ?"
            params.append(str(uid))
        if not include_deleted:
            sql += " AND deleted = 0"
        sql += " ORDER BY ts DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        conn = _get_conn()
        with _lock:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "uid": _uid,
                "id": item_id,
                "content": content,
                "pic_url": json.loads(pic) if pic is not None else None,
                "ts": ts,
                "deleted": bool(deleted),
                "deleted_at": deleted_at,
            }
            for _uid, item_id, content, pic, ts, deleted, deleted_at in rows
        ]
    except Exception as e:
        _log("error", f"查询动态失败 platform={platform}: {e}")
        return []
