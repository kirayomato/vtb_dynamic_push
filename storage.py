"""持久化存储模块

基于 SQLite 的本地状态存储，解决程序重启后所有内存状态丢失、
必须重新从头初始化的问题，同时支持离线查询历史数据。

- kv 表: 存储 uid -> 任意JSON值 的键值状态（昵称/头像/签名/直播状态/计数等）
- dynamics 表: 存储各平台的动态/微博/文章 (platform, uid, item_id, content, pic_url, ts)

线程安全（RLock + WAL 模式），所有写入失败仅记录日志，不影响查询主流程。

文件末尾另提供一套只读查询接口（list_tables / table_schema / run_readonly_query），
供 web 端「SQL 浏览器」使用，写入被 SQLite 内核级拦截。
"""

import atexit
import json
import os
import re
import sqlite3
import threading
import time
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


def db_path() -> str:
    """当前持久化数据库文件路径（供只读浏览器等展示用）。"""
    return _db_path()


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


# ---------------- 只读 SQL 浏览器 ----------------
#
# 只读边界由五层共同保证，任何一层单独失效都不会导致数据被改写：
#   1. 语句白名单：只放行 SELECT / WITH / VALUES / EXPLAIN / PRAGMA 开头的语句，
#      UPDATE、DROP、ATTACH 等在入口就被拒绝，并给出可读的报错；
#   2. PRAGMA 黑名单：journal_mode / writable_schema / query_only 等会改动库文件
#      或连接状态的 pragma 被单独拒绝（query_only 放行等于自废只读开关）；
#   3. PRAGMA query_only=ON：SQLite 内核级只读开关，即使白名单有遗漏，
#      prepare 阶段也会拒绝任何改写数据库的语句；
#   4. set_authorizer 拒绝 INSERT/UPDATE/DELETE/DDL/ATTACH 等动作码，作兜底；
#   5. Python 的 cursor.execute 原生只接受单条语句，`SELECT 1;DROP ...` 这类
#      堆叠语句会直接抛 ProgrammingError，无法绕过。
# 只读连接独立于写入连接，彼此不共享状态，查询由专用锁串行化。

#: 单次查询最多返回的行数，防止一次把整库拉进浏览器
SQL_BROWSE_MAX_ROWS = 1000
#: 单次查询最长执行时间（秒），超时由 progress_handler 中断
SQL_BROWSE_TIMEOUT = 5.0
#: 单个单元格文本超过该长度就截断，避免超大 JSON 撑爆响应体
SQL_CELL_MAX_CHARS = 4000
#: 白名单：只有这些关键字开头的语句才允许执行
_SQL_READ_KEYWORDS = ("select", "with", "values", "explain", "pragma")
#: 禁止的 PRAGMA：这些会改动库文件/连接状态，属于"写"而非"读"
#: （query_only 也在其中，防止只读开关被自己关掉；writable_schema 是经典绕过手法）
_SQL_DENY_PRAGMAS = frozenset(
    (
        "journal_mode",
        "writable_schema",
        "synchronous",
        "locking_mode",
        "auto_vacuum",
        "page_size",
        "secure_delete",
        "journal_size_limit",
        "max_page_count",
        "reserve_size",
        "cell_size",
        "legacy_file_format",
        "wal_checkpoint",
        "incremental_vacuum",
        "optimize",
        "query_only",
        "trusted_schema",
        "cache_spill",
        "mmap_size",
    )
)
#: 授权器拒绝的动作码（写数据 / 改结构 / 挂载其它库）
_SQL_DENY_ACTIONS = frozenset(
    getattr(sqlite3, _name)
    for _name in (
        "SQLITE_INSERT",
        "SQLITE_UPDATE",
        "SQLITE_DELETE",
        "SQLITE_CREATE_INDEX",
        "SQLITE_CREATE_TABLE",
        "SQLITE_CREATE_TEMP_INDEX",
        "SQLITE_CREATE_TEMP_TABLE",
        "SQLITE_CREATE_TEMP_TRIGGER",
        "SQLITE_CREATE_TEMP_VIEW",
        "SQLITE_CREATE_TRIGGER",
        "SQLITE_CREATE_VIEW",
        "SQLITE_CREATE_VTABLE",
        "SQLITE_DROP_INDEX",
        "SQLITE_DROP_TABLE",
        "SQLITE_DROP_TEMP_INDEX",
        "SQLITE_DROP_TEMP_TABLE",
        "SQLITE_DROP_TEMP_TRIGGER",
        "SQLITE_DROP_TEMP_VIEW",
        "SQLITE_DROP_TRIGGER",
        "SQLITE_DROP_VIEW",
        "SQLITE_DROP_VTABLE",
        "SQLITE_ALTER_TABLE",
        "SQLITE_REINDEX",
        "SQLITE_ANALYZE",
        "SQLITE_ATTACH",
        "SQLITE_DETACH",
        "SQLITE_SAVEPOINT",
        "SQLITE_TRANSACTION",
    )
)

_ro_conn = None
_sql_lock = threading.RLock()


def _sql_authorizer(action, arg1, arg2, db_name, source):
    """SQLite 授权回调：拒绝一切写数据/改结构/挂载库的动作。"""
    if action in _SQL_DENY_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and (arg1 or "").lower() in _SQL_DENY_PRAGMAS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _get_read_conn() -> sqlite3.Connection:
    """惰性创建只读查询专用连接。

    没有用 `mode=ro` 的 URI 打开：WAL 库在只读模式下仍要求 -shm 可写，
    进程刚启动、-shm 尚未建立时会直接打开失败。这里改为普通连接 +
    `PRAGMA query_only=ON` + authorizer，兼容性更好，写入同样被内核拒绝。
    """
    global _ro_conn
    with _sql_lock:
        if _ro_conn is not None:
            return _ro_conn
        path = _db_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=3000")
        conn.set_authorizer(_sql_authorizer)
        _ro_conn = conn
    _log("info", "只读查询连接已建立（SQL 浏览器）")
    return _ro_conn


def _close_read_conn() -> None:
    global _ro_conn
    with _sql_lock:
        if _ro_conn is None:
            return
        try:
            _ro_conn.close()
        except Exception as e:
            _log("error", f"关闭只读连接失败: {e}")
        _ro_conn = None


atexit.register(_close_read_conn)


def _quote_ident(name: str) -> str:
    """把标识符安全地包成 SQLite 双引号形式，内部双引号翻倍。"""
    return '"' + str(name).replace('"', '""') + '"'


def _strip_sql_comments(sql: str) -> str:
    """去掉 SQL 中的 -- 行注释与 /* */ 块注释，便于取首个关键字。"""
    out = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j + 1
        elif ch == "/" and sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def sql_first_keyword(sql: str) -> str:
    """返回语句的首个关键字（小写），空语句返回空串。"""
    m = re.match(r"[A-Za-z_]+", _strip_sql_comments(sql or "").lstrip())
    return m.group(0).lower() if m else ""


def _sql_pragma_name(sql: str) -> str:
    """取出 PRAGMA 语句的目标名（小写），兼容 `PRAGMA main.xxx` 写法。"""
    body = _strip_sql_comments(sql or "").strip()
    m = re.match(r"(?i)pragma\s+(?:[A-Za-z_]\w*\s*\.\s*)?([A-Za-z_]\w*)", body)
    return m.group(1).lower() if m else ""


def _json_cell(value):
    """把 sqlite 返回值规整成可 JSON 序列化的形式，超长文本截断。"""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<BLOB {len(bytes(value))} bytes>"
    if isinstance(value, str) and len(value) > SQL_CELL_MAX_CHARS:
        return value[:SQL_CELL_MAX_CHARS] + f"…（已截断，共 {len(value)} 字符）"
    return value


def list_tables() -> list:
    """列出所有表/视图及行数，供 SQL 浏览器侧栏展示。

    返回 [{name, type, rows}]；视图或统计失败时 rows 为 None。
    """
    try:
        conn = _get_read_conn()
        with _sql_lock:
            tables = conn.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
                "ORDER BY type, name"
            ).fetchall()
            result = []
            for name, kind in tables:
                try:
                    rows = conn.execute(
                        f"SELECT COUNT(*) FROM {_quote_ident(name)}"
                    ).fetchone()[0]
                except sqlite3.Error:
                    rows = None
                result.append({"name": name, "type": kind, "rows": rows})
        return result
    except Exception as e:
        _log("error", f"读取表列表失败: {e}")
        return []


def table_schema(table: str) -> dict:
    """返回指定表/视图的字段、索引与建表语句。

    表名先到 sqlite_master 里核对，避免把用户输入直接拼进 SQL。
    """
    try:
        conn = _get_read_conn()
        with _sql_lock:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') "
                "AND name = ?",
                (table,),
            ).fetchone()
            if not exists:
                return {"error": f"表不存在: {table}"}
            cols = conn.execute(
                f"PRAGMA table_info({_quote_ident(table)})"
            ).fetchall()
            indexes = conn.execute(
                f"PRAGMA index_list({_quote_ident(table)})"
            ).fetchall()
            ddl = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = ?", (table,)
            ).fetchone()
        return {
            "table": table,
            "columns": [
                {
                    "name": c[1],
                    "type": c[2],
                    "notnull": bool(c[3]),
                    "default": c[4],
                    "pk": bool(c[5]),
                }
                for c in cols
            ],
            "indexes": [
                {"name": i[1], "unique": bool(i[2])} for i in indexes
            ],
            "sql": ddl[0] if ddl else None,
        }
    except Exception as e:
        _log("error", f"读取表结构失败 table={table}: {e}")
        return {"error": f"读取表结构失败: {e}"}


def run_readonly_query(sql: str, limit: int = None, timeout: float = None) -> dict:
    """执行一条只读 SQL，返回结果集。

    成功时返回 {columns, rows, row_count, truncated, limit, elapsed_ms}；
    被拒或出错时返回 {error, sql_error?}。只允许单条 SELECT/WITH/VALUES/
    EXPLAIN/PRAGMA 语句，超出 limit 的行丢弃并置 truncated=True，
    执行超过 timeout 秒会被自动中断。
    """
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return {"error": "SQL 不能为空", "sql_error": True}

    keyword = sql_first_keyword(sql)
    if keyword not in _SQL_READ_KEYWORDS:
        allowed = " / ".join(k.upper() for k in _SQL_READ_KEYWORDS)
        return {
            "error": f"只读模式仅支持 {allowed} 语句，"
            f"当前语句以 {(keyword.upper() or '(空)')} 开头",
            "sql_error": True,
        }

    if keyword == "pragma":
        pragma = _sql_pragma_name(sql)
        if pragma in _SQL_DENY_PRAGMAS:
            return {
                "error": f"只读模式禁止修改数据库状态：PRAGMA {pragma}",
                "sql_error": True,
            }

    if limit is None:
        limit = SQL_BROWSE_MAX_ROWS
    else:
        limit = max(1, min(int(limit), SQL_BROWSE_MAX_ROWS))
    timeout = SQL_BROWSE_TIMEOUT if timeout is None else max(0.1, float(timeout))

    conn = _get_read_conn()
    start = time.monotonic()
    deadline = start + timeout

    def _watchdog():
        # 返回非 0 会让 SQLite 中断当前语句
        return 1 if time.monotonic() > deadline else 0

    try:
        with _sql_lock:
            conn.set_progress_handler(_watchdog, 20000)
            try:
                cur = conn.execute(sql)
                columns = [d[0] for d in (cur.description or [])]
                raw = cur.fetchmany(limit + 1)  # 多取一行用于判断是否被截断
            finally:
                conn.set_progress_handler(None, 0)
        truncated = len(raw) > limit
        rows = [[_json_cell(v) for v in row] for row in raw[:limit]]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "limit": limit,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
        }
    except sqlite3.OperationalError as e:
        msg = str(e)
        low = msg.lower()
        if "interrupt" in low:
            msg = f"查询超时（>{timeout:g}s）已中断，请用 WHERE / LIMIT 缩小范围"
        elif "authoriz" in low:
            msg = "当前为只读模式，禁止 INSERT/UPDATE/DELETE 及结构变更"
        elif "readonly" in low:
            msg = "数据库为只读状态，写操作被拒绝"
        return {"error": msg, "sql_error": True}
    except sqlite3.Error as e:
        msg = str(e)
        if "one statement at a time" in msg:
            msg = "一次只能执行一条语句，不支持用分号堆叠多条语句"
        return {"error": msg, "sql_error": True}
    except Exception as e:
        _log("error", f"只读查询失败: {e}")
        return {"error": f"查询失败: {e}", "sql_error": True}
