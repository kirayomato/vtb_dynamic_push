"""内容变化检测与 dynamics 多版本存储的回归测试。

零网络请求；所有数据库操作都落在 tempfile 临时目录，不触碰真实 data/state.db。

运行（用装了 requirements.txt 的解释器，项目根目录执行）：
    python -m unittest discover -s unit_test -p "test_content_change.py" -v
"""

import calendar
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import storage
from utils import (
    CHANGED,
    NEW,
    OLD_NEW,
    UNCHANGED,
    Fetch,
    classify_item,
    content_diff,
    id_key,
)


class IDKeyTests(unittest.TestCase):
    def test_numeric_ids_compare_by_value_not_by_string(self):
        # B 站库里实测同时存在 18 位与 19 位 id：字符串序会把 19 位新动态
        # 判成比 18 位旧动态更小，进而漏推 / 误判删除。
        old_18 = "582979018019395013"
        new_19 = "1000092794261340169"
        self.assertGreater(old_18, new_19)  # 字符串序确实是反的
        self.assertLess(id_key(old_18), id_key(new_19))

    def test_same_length_numeric_and_int_input(self):
        self.assertLess(id_key("4725453057951623"), id_key("5365500513095420"))
        self.assertEqual(id_key("123"), id_key(123))

    def test_non_numeric_falls_back_to_lexicographic(self):
        a = "abf39bc68cc011f0b5495254001e7c00"
        b = "e6ad47b090af11f0b32e52540025c377"
        self.assertLess(id_key(a), id_key(b))
        self.assertLess(id_key(a), id_key("123"))


class ContentDiffTests(unittest.TestCase):
    def test_no_change(self):
        diff = content_diff(("原文", ["a.jpg"]), ("原文", ["a.jpg"]))
        self.assertFalse(diff.changed)
        self.assertEqual(diff.fields, "无")

    def test_same_picture_with_different_query_is_not_a_change(self):
        diff = content_diff(
            ("原文", ["https://img/a.jpg?token=1"]),
            ("原文", ["https://img/a.jpg?token=2"]),
        )
        self.assertFalse(diff.pics_changed)
        self.assertFalse(diff.changed)

    def test_text_changed_summary_has_before_and_after(self):
        diff = content_diff(("旧文", None), ("新文", None))
        self.assertTrue(diff.changed)
        self.assertTrue(diff.text_changed)
        self.assertFalse(diff.pics_changed)
        self.assertIn("【修改前】", diff.summary())
        self.assertIn("【修改后】", diff.summary())
        self.assertEqual(diff.fields, "文字")

    def test_push_summary_fits_notify_limit_and_shows_both_sides(self):
        # notify() 在 200 字处硬截断正文，push_summary 必须让「前」「后」都露出来
        diff = content_diff(("旧" * 300, None), ("新" * 300, None))
        body = diff.push_summary()
        self.assertLess(len(body), 200)
        self.assertIn("前：", body)
        self.assertIn("后：", body)
        self.assertIn("新" * 10, body[body.index("后："):])
        # 图片变化也要带上，且整条推送同样不超预算
        pics = content_diff(("同", ["a.jpg", "b.jpg"]), ("同", ["a.jpg"]))
        self.assertIn("图片：2 -> 1 张", pics.push_summary())

    def test_pics_changed_str_list_and_none(self):
        diff = content_diff(("同", ["a.jpg", "b.jpg"]), ("同", ["a.jpg"]))
        self.assertTrue(diff.pics_changed)
        self.assertIn("2 张 -> 1 张", diff.summary())
        self.assertTrue(content_diff(("同", None), ("同", "a.jpg")).pics_changed)
        self.assertTrue(content_diff(("同", "a.jpg"), ("同", "b.jpg")).pics_changed)

    def test_both_fields_and_none_text(self):
        diff = content_diff((None, None), ("新", ["a.jpg"]))
        self.assertEqual(diff.fields, "文字、图片")
        self.assertFalse(content_diff((None, None), ("", None)).changed)

    def test_accepts_three_tuple_from_dynamic_dict(self):
        diff = content_diff(("旧", ["a.jpg"], 100.0), ("新", ["a.jpg"], 100.0))
        self.assertTrue(diff.text_changed)
        self.assertFalse(diff.pics_changed)

    def test_forward_name_change_is_not_a_content_change(self):
        # 转发人改名不该算作者改了正文；正文里其余差异仍要检出
        head = "你听我说吨吨桶真的很治愈呀....\n\n"
        tail = "**的动态：\n> 吨吨桶🫵🏻‼️"
        diff = content_diff(
            (head + "转发**-吃饭高手-" + tail, ["a.png"]),
            (head + "转发**雨纪家的吃饭低手" + tail, ["a.png"]),
        )
        self.assertFalse(diff.text_changed)
        self.assertFalse(diff.changed)

        diff = content_diff(
            ("你听我说吨吨桶真的很治愈呀....\n\n转发**-吃饭高手-**的动态：", None),
            ("你听我说吨吨桶真的很治愈呀....\n\n转发**-吃饭高手-**的转发：", None),
        )
        self.assertTrue(diff.text_changed)


class ClassifyItemTests(unittest.TestCase):
    def setUp(self):
        self.known = {
            "100": ("原文", ["a.jpg"], 100.0),
            "90": ("更早", None, 90.0),
        }

    def test_new_is_above_max_id(self):
        status, diff = classify_item("110", "新", None, self.known, "100")
        self.assertEqual(status, NEW)
        self.assertIsNone(diff)

    def test_old_id_not_filtered(self):
        # 旧 id 但首次见到：仍然要入库（OLD_NEW），只是不推送
        status, diff = classify_item("95", "历史", None, self.known, "100")
        self.assertEqual(status, OLD_NEW)
        self.assertIsNone(diff)

    def test_changed_and_unchanged(self):
        status, diff = classify_item("100", "改了", ["a.jpg"], self.known, "100")
        self.assertEqual(status, CHANGED)
        self.assertTrue(diff.text_changed)

        status, diff = classify_item("100", "原文", ["a.jpg"], self.known, "100")
        self.assertEqual(status, UNCHANGED)
        self.assertIsNone(diff)

    def test_mixed_length_ids_still_classified_as_new(self):
        known = {"582979018019395013": ("旧", None, 1.0)}
        status, _ = classify_item(
            "1000092794261340169", "新", None, known, "582979018019395013"
        )
        self.assertEqual(status, NEW)

    def test_max_id_is_snapshot_within_one_round(self):
        # 同一轮里连续两条新动态，max_id 固定为循环开始前的 100
        first, _ = classify_item("110", "A", None, self.known, "100")
        second, _ = classify_item("109", "B", None, self.known, "100")
        self.assertEqual((first, second), (NEW, NEW))


_LEGACY_DDL = """CREATE TABLE dynamics (
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
)"""


class StorageVersionTests(unittest.TestCase):
    """每个用例用独立的临时库，验证多版本读写与旧库迁移。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vtb_dyn_")
        self.db_path = os.path.join(self.tmp.name, "state.db")
        self._orig_db_path = storage._db_path
        self._orig_log = storage._log
        storage._db_path = lambda: self.db_path
        storage._log = lambda *a, **k: None
        storage.close()
        storage._close_read_conn()

    def tearDown(self):
        storage.close()
        storage._close_read_conn()
        storage._db_path = self._orig_db_path
        storage._log = self._orig_log
        self.tmp.cleanup()

    def _conn(self):
        return storage._get_conn()

    def _create_legacy_db(self, rows, with_deleted=True):
        conn = sqlite3.connect(self.db_path)
        ddl = _LEGACY_DDL if with_deleted else _LEGACY_DDL.replace(
            "    deleted INTEGER NOT NULL DEFAULT 0,\n    deleted_at REAL,\n", ""
        )
        conn.execute(ddl)
        if with_deleted:
            conn.executemany(
                "INSERT INTO dynamics "
                "(platform, uid, item_id, content, pic_url, ts, deleted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        else:
            conn.executemany(
                "INSERT INTO dynamics (platform, uid, item_id, content, pic_url, ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [r[:6] for r in rows],
            )
        conn.commit()
        conn.close()

    def test_migration_keeps_rows_and_adds_revision(self):
        self._create_legacy_db(
            [
                ("bili", "1", "a1", "旧文", json.dumps(["a.jpg"]), 100.0, 0),
                ("bili", "1", "a2", "另一条", None, 200.0, 0),
                ("bili", "1", "a3", "已删除", None, 300.0, 1),
            ]
        )
        conn = self._conn()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(dynamics)")]
        self.assertIn("revision", cols)
        self.assertIn("edited_at", cols)
        pk = [r[1] for r in conn.execute("PRAGMA table_info(dynamics)") if r[5]]
        self.assertEqual(pk, ["platform", "uid", "item_id", "revision"])
        self.assertEqual(
            conn.execute("SELECT COUNT(*), MIN(revision), MAX(revision) FROM dynamics")
            .fetchone(),
            (3, 0, 0),
        )
        loaded = storage.dyn_load("bili")
        self.assertEqual(set(loaded["1"]), {"a1", "a2"})  # 软删除行不还原
        self.assertEqual(loaded["1"]["a1"][1], ["a.jpg"])

    def test_migration_handles_legacy_db_without_deleted_columns(self):
        self._create_legacy_db(
            [("weibo", "2", "w1", "老数据", None, 10.0, 0)], with_deleted=False
        )
        conn = self._conn()
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM dynamics").fetchone()[0], 1
        )
        self.assertEqual(storage.dyn_load("weibo")["2"]["w1"][0], "老数据")

    def test_commit_keeps_history_and_load_only_latest(self):
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "v0", ["a.jpg"], 100.0, memory)
        self.assertEqual(
            storage.dyn_commit("bili", "1", "a1", "v1", ["b.jpg"], 100.0, memory), 1
        )
        self.assertEqual(
            storage.dyn_commit("bili", "1", "a1", "v2", None, 100.0, memory), 2
        )
        loaded = storage.dyn_load("bili")
        self.assertEqual(len(loaded["1"]), 1)
        self.assertEqual(loaded["1"]["a1"], ("v2", None, 100.0))

        rows = storage.dyn_query("bili", item_id="a1")
        self.assertEqual([r["revision"] for r in rows], [2, 1, 0])
        self.assertEqual([r["content"] for r in rows], ["v2", "v1", "v0"])
        self.assertIsNone(rows[-1]["edited_at"])
        self.assertIsNotNone(rows[0]["edited_at"])
        self.assertEqual(rows[-1]["pic_url"], ["a.jpg"])

    def test_restore_limit_counts_items_not_versions(self):
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory)
        storage.dyn_commit("bili", "1", "a1", "v1", None, 100.0, memory)
        storage.dyn_commit("bili", "1", "a1", "v2", None, 100.0, memory)
        storage.dyn_commit("bili", "1", "a2", "另一条", None, 200.0, memory)
        loaded = storage.dyn_load("bili", limit=2)
        self.assertEqual(set(loaded["1"]), {"a1", "a2"})
        self.assertEqual(loaded["1"]["a1"][0], "v2")

    def test_del_marks_every_version(self):
        memory = {}
        storage.dyn_commit("weibo", "2", "w1", "v0", None, 10.0, memory)
        storage.dyn_commit("weibo", "2", "w1", "v1", None, 10.0, memory)
        storage.dyn_del("weibo", "2", "w1")
        self.assertEqual(storage.dyn_load("weibo"), {})
        rows = storage.dyn_query("weibo", item_id="w1", include_deleted=True)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["deleted"] for r in rows))

    def test_set_many_writes_revision_zero(self):
        storage.dyn_set_many(
            "afd",
            "u",
            {"x1": ("A", None, 1.0), "x2": ("B", ["p.jpg"], 2.0)},
        )
        rows = storage.dyn_query("afd")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["revision"] == 0 for r in rows))
        self.assertEqual(storage.dyn_load("afd")["u"]["x2"][1], ["p.jpg"])

    def test_set_many_never_overwrites_existing_versions(self):
        # 回归：初始化重入（内存为空但库里已有编辑历史）不能把 rev0 原始版本
        # 覆盖成当前 feed，也不能改变 dyn_load 取到的最新版本。
        memory = {}
        storage.dyn_commit("weibo", "2", "w1", "v0", None, 10.0, memory)
        storage.dyn_commit("weibo", "2", "w1", "v1", None, 10.0, memory)
        storage.dyn_set_many(
            "weibo",
            "2",
            {"w1": ("当前feed", None, 10.0), "w2": ("新条目", None, 11.0)},
        )
        rows = storage.dyn_query("weibo", item_id="w1")
        self.assertEqual([r["content"] for r in rows], ["v1", "v0"])
        self.assertEqual(storage.dyn_load("weibo")["2"]["w1"][0], "v1")
        self.assertIn("w2", storage.dyn_load("weibo")["2"])

    def test_commit_after_delete_revives_and_appends(self):
        # 动态被误删后又改过：软删除后写回新内容，追加版本 + 复活所有版本行
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory)
        storage.dyn_commit("bili", "1", "a1", "v1", None, 100.0, memory)
        storage.dyn_del("bili", "1", "a1")
        storage.dyn_commit("bili", "1", "a1", "again", None, 100.0, memory)
        rows = storage.dyn_query("bili", item_id="a1", include_deleted=True)
        self.assertEqual([r["revision"] for r in rows], [2, 1, 0])
        self.assertTrue(all(not r["deleted"] for r in rows))
        self.assertEqual(rows[0]["content"], "again")
        self.assertEqual(storage.dyn_load("bili")["1"]["a1"][0], "again")

    def test_failed_migration_does_not_cache_broken_conn(self):
        # 回归：迁移失败若把连接缓存下来，之后迁移永不重试、所有读写只剩 error 日志
        self._create_legacy_db(
            [("bili", "1", "a1", "旧文", None, 100.0, 0)]
        )
        boom = mock.patch.object(
            storage,
            "_migrate_dynamics_to_versions",
            side_effect=RuntimeError("模拟迁移失败"),
        )
        with boom:
            self.assertEqual(storage.dyn_load("bili"), {})
            self.assertIsNone(storage._conn)
        # 恢复正常后下一次调用应重新迁移成功
        self.assertEqual(storage.dyn_load("bili")["1"]["a1"][0], "旧文")
        cols = [r[1] for r in storage._conn.execute("PRAGMA table_info(dynamics)")]
        self.assertIn("revision", cols)

    def test_migration_succeeds_on_nonempty_legacy_db_without_updated_at(self):
        # 回归：老库有数据、且连 updated_at 列都没有时，迁移必须成功。
        # SQLite 不允许 ALTER TABLE ADD COLUMN 带非恒定默认值，
        # 原实现用 "REAL NOT NULL DEFAULT (strftime('%s','now'))" 补这一列，
        # 在非空表上直接抛 "Cannot add a column with non-constant default"，
        # 整个迁移回滚 -> 之后所有持久化读写只剩 error 日志。
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE dynamics ("
            " platform TEXT NOT NULL, uid TEXT NOT NULL, item_id TEXT NOT NULL,"
            " content TEXT, pic_url TEXT, ts REAL,"
            " deleted INTEGER NOT NULL DEFAULT 0, deleted_at REAL,"
            " PRIMARY KEY (platform, uid, item_id))"
        )
        conn.executemany(
            "INSERT INTO dynamics (platform, uid, item_id, content, pic_url, ts,"
            " deleted, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("bili", "1", "a1", "旧文", None, 100.0, 0, None),
                ("bili", "1", "a2", "另一条", None, 200.0, 0, None),
            ],
        )
        conn.commit()
        conn.close()

        loaded = storage.dyn_load("bili")
        self.assertEqual(set(loaded["1"]), {"a1", "a2"})
        self.assertEqual(loaded["1"]["a1"][0], "旧文")
        cols = [r[1] for r in storage._conn.execute("PRAGMA table_info(dynamics)")]
        self.assertIn("revision", cols)
        self.assertIn("updated_at", cols)
        # 补出来的 updated_at 不能是 NULL（NOT NULL 列）
        nulls = storage._conn.execute(
            "SELECT COUNT(*) FROM dynamics WHERE updated_at IS NULL"
        ).fetchone()[0]
        self.assertEqual(nulls, 0)


class DynCommitTests(unittest.TestCase):
    """dyn_commit：内存字典与表一起更新的组合语义。

    内存存「当前看到的样子」，表存版本历史，两者必须同时更新，
    否则下一轮的变更比对会失去基准。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vtb_commit_")
        self.db_path = os.path.join(self.tmp.name, "state.db")
        self._orig_db_path = storage._db_path
        self._orig_log = storage._log
        storage._db_path = lambda: self.db_path
        storage._log = lambda *a, **k: None
        storage.close()
        storage._close_read_conn()

    def tearDown(self):
        storage.close()
        storage._close_read_conn()
        storage._db_path = self._orig_db_path
        storage._log = self._orig_log
        self.tmp.cleanup()

    def _rows(self, platform="bili", uid="1", item_id="a1"):
        return storage.dyn_query(
            platform, uid=uid, item_id=item_id, include_deleted=True
        )

    def test_commit_writes_revision_zero_for_new_item(self):
        memory = {}
        rev = storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory)
        self.assertEqual(rev, 0)
        rows = self._rows()
        self.assertEqual([r["revision"] for r in rows], [0])
        self.assertEqual(rows[0]["content"], "v0")
        # rev0 是「首次抓到的版本」，不是一次编辑，不该有编辑时间
        self.assertIsNone(rows[0]["edited_at"])

    def test_commit_is_idempotent_when_content_unchanged(self):
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory)
        self.assertEqual(
            storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory), 0
        )
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["revision"], 0)

    def test_commit_appends_revision_when_content_changed(self):
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory)
        self.assertEqual(
            storage.dyn_commit("bili", "1", "a1", "v1", None, 100.0, memory), 1
        )
        rows = self._rows()
        self.assertEqual([r["revision"] for r in rows], [1, 0])
        self.assertEqual([r["content"] for r in rows], ["v1", "v0"])
        self.assertIsNotNone(rows[0]["edited_at"])

    def test_commit_never_overwrites_edit_history(self):
        # 核心回归：连改三次，中间版本必须都在
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "原文", None, 100.0, memory)
        storage.dyn_commit("bili", "1", "a1", "改过一次", None, 100.0, memory)
        storage.dyn_commit("bili", "1", "a1", "改了两次", None, 100.0, memory)
        rows = self._rows()
        self.assertEqual([r["revision"] for r in rows], [2, 1, 0])
        self.assertEqual(
            [r["content"] for r in rows], ["改了两次", "改过一次", "原文"]
        )

    def test_commit_preserves_history_across_restart(self):
        # 回归：进程重启（内存清空）后再看到被改过的动态，中间版本不能丢
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "原文", None, 100.0, memory)
        storage.dyn_commit("bili", "1", "a1", "改过一次", None, 100.0, memory)
        storage.close()  # 模拟重启：连接关掉，内存状态全丢
        storage.dyn_commit("bili", "1", "a1", "改了两次", None, 100.0, {})
        rows = self._rows()
        self.assertEqual(
            [r["content"] for r in rows], ["改了两次", "改过一次", "原文"]
        )

    def test_commit_revives_deleted_item_without_new_version(self):
        # 回归：动态被误判删除后又回到 feed（删除检测只看 feed 内容，
        # 平台少返回几条就会误判）——必须复活，且不能凭空多出一个版本
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory)
        storage.dyn_del("bili", "1", "a1")
        self.assertEqual(storage.dyn_load("bili"), {})
        self.assertEqual(
            storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory), 0
        )
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["deleted"])
        self.assertEqual(rows[0]["content"], "v0")
        self.assertEqual(storage.dyn_load("bili")["1"]["a1"][0], "v0")

    def test_commit_ignores_image_signature_change(self):
        # 图床换签名参数不是「换了图」，不该刷出版本行
        memory = {}
        storage.dyn_commit(
            "bili", "1", "a1", "带图", ["https://x/a.jpg?sign=aaa"], 100.0, memory
        )
        rev = storage.dyn_commit(
            "bili", "1", "a1", "带图", ["https://x/a.jpg?sign=bbb"], 100.0, memory
        )
        self.assertEqual(rev, 0)
        self.assertEqual(len(self._rows()), 1)

    def test_commit_detects_real_image_change(self):
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "带图", ["https://x/a.jpg"], 100.0, memory)
        rev = storage.dyn_commit(
            "bili", "1", "a1", "带图", ["https://x/b.jpg"], 100.0, memory
        )
        self.assertEqual(rev, 1)
        self.assertEqual(len(self._rows()), 2)

    def test_commit_updates_memory_and_table_together(self):
        memory = {}
        rev = storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory)
        self.assertEqual(rev, 0)
        self.assertEqual(memory["a1"], ("v0", None, 100.0))
        rows = storage.dyn_query("bili", uid="1", item_id="a1")
        self.assertEqual(rows[0]["content"], "v0")

    def test_commit_memory_keeps_old_ts_on_edit(self):
        # 编辑不改发布时间：内存与表都要沿用旧 ts，不能用本轮传入的 ts
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory)
        storage.dyn_commit("bili", "1", "a1", "v1", None, 200.0, memory)
        self.assertEqual(memory["a1"][2], 100.0)
        rows = storage.dyn_query("bili", uid="1", item_id="a1")
        self.assertEqual(rows[0]["ts"], 100.0)

    def test_commit_memory_ts_matches_table_ts(self):
        # 内存与表在 ts 上不能错位：否则下一轮比对会把发布时间当成变了
        memory = {}
        storage.dyn_commit("bili", "1", "a1", "v0", None, 100.0, memory)
        storage.dyn_commit("bili", "1", "a1", "v1", None, 999.0, memory)
        rows = storage.dyn_query("bili", uid="1", item_id="a1")
        self.assertEqual(memory["a1"][2], rows[0]["ts"])

    def test_commit_failure_still_updates_memory(self):
        # 落库失败不应该回滚内存：内存记录的是「本轮看到的样子」，
        # 下一轮重新比对时仍应以它为基准
        memory = {}
        boom = mock.patch.object(
            storage, "_get_conn", side_effect=RuntimeError("模拟连库失败")
        )
        with boom:
            rev = storage.dyn_commit("bili", "1", "a1", "v0", None, 1.0, memory)
        self.assertEqual(rev, -1)
        self.assertEqual(memory["a1"], ("v0", None, 1.0))


class _StubConfig:
    """隔离真实 config.ini / Cookie，避免测试受本机配置影响。"""

    WeiboCookies = {}

    def get(self, section, name, default=None):
        return {
            "special_list": "",
            "enable_cookie_check": "false",
            "save_video": "false",
        }.get(name, default)


class _Reporter:
    def set_status(self, *args, **kwargs):
        pass


def _response(cards, total=100):
    return {"ok": 1, "data": {"cards": cards, "cardlistInfo": {"total": total}}}


def _card(item_id, text, created, uid):
    """最小的 card_type=9 微博，字段够 query_weibodynamic 解析即可。"""
    return {
        "card_type": 9,
        "scheme": f"https://m.weibo.cn/detail/{item_id}",
        "mblog": {
            "id": str(item_id),
            "text": text,
            "raw_text": text,
            "created_at": created,
            "user": {
                "id": int(uid),
                "screen_name": "测试",
                "profile_image_url": "https://img/face.jpg",
                "description": "签名",
            },
        },
    }


class WeiboLoopTests(unittest.TestCase):
    """用 mock 的 feed 跑真实查询循环，验证通知决策与编辑版本落库。

    只隔离网络/媒体/通知/配置，storage 走临时真实库，因此能同时验证入库结果。
    """

    UID = "9999999999"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vtb_weibo_")
        self.db_path = os.path.join(self.tmp.name, "state.db")
        self._orig_db_path = storage._db_path
        self._orig_log = storage._log
        storage._db_path = lambda: self.db_path
        storage._log = lambda *a, **k: None
        storage.close()
        storage._close_read_conn()

        import query_weibo as qw

        self.qw = qw
        for state in (
            qw.DYNAMIC_DICT,
            qw.USER_FACE_DICT,
            qw.USER_SIGN_DICT,
            qw.USER_NAME_DICT,
            qw.USER_COUNT_DICT,
            qw._SPECIAL_BACKFILLED,
        ):
            state.clear()
        self._orig_config = qw.config
        qw.config = _StubConfig()

        # 用英文星期/月份缩写，避开中文 locale 下 strptime %a/%b 解析失败
        dt = datetime.now() - timedelta(hours=1)
        self.created = (
            f"{calendar.day_abbr[dt.weekday()]} {calendar.month_abbr[dt.month]} "
            f"{dt.day:02d} {dt:%H:%M:%S} +0800 {dt.year}"
        )

    def tearDown(self):
        self.qw.config = self._orig_config
        storage.close()
        storage._close_read_conn()
        storage._db_path = self._orig_db_path
        storage._log = self._orig_log
        self.tmp.cleanup()

    def _card(self, item_id, text):
        return _card(item_id, text, self.created, self.UID)

    def _run(self, cards):
        """跑一轮 query_weibodynamic，返回 (结果, 本轮推送标题列表)。"""
        resp = _response(cards)
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(self.qw, "fetch_json", return_value=Fetch(data=resp))
            )
            stack.enter_context(mock.patch.object(self.qw, "get_icon", return_value=None))
            stack.enter_context(mock.patch.object(self.qw, "get_image", return_value=None))
            stack.enter_context(mock.patch.object(self.qw, "save_videos"))
            notify_mock = stack.enter_context(mock.patch.object(self.qw, "notify"))
            result = self.qw.query_weibodynamic(self.UID, _Reporter())
            titles = [call.args[0] for call in notify_mock.call_args_list]
        return result, titles

    def _init_feed(self):
        return [self._card("100", "原文"), self._card("90", "更早")]

    def test_old_id_is_stored_but_never_notified(self):
        result, titles = self._run(self._init_feed())  # 首轮初始化
        self.assertIsInstance(result, int)
        self.assertEqual(titles, [])

        feed = [
            self._card("100", "原文"),
            self._card("95", "历史微博"),  # 旧 id，首次见到
            self._card("90", "更早"),
        ]
        result, titles = self._run(feed)
        self.assertIsInstance(result, int)
        self.assertFalse(any("微博更新" in t or "转发微博" in t for t in titles))
        self.assertIn("95", self.qw.DYNAMIC_DICT[self.UID])
        self.assertIn("95", storage.dyn_load("weibo")[self.UID])

    def test_content_change_notifies_and_keeps_edit_history(self):
        self._run(self._init_feed())

        changed = [self._card("100", "改了"), self._card("90", "更早")]
        _, titles = self._run(changed)
        self.assertTrue(any("修改了微博" in t for t in titles))
        self.assertEqual(self.qw.DYNAMIC_DICT[self.UID]["100"][0], "改了")
        rows = storage.dyn_query("weibo", item_id="100")
        self.assertEqual([r["revision"] for r in rows], [1, 0])
        self.assertEqual([r["content"] for r in rows], ["改了", "原文"])
        self.assertEqual(storage.dyn_load("weibo")[self.UID]["100"][0], "改了")

        # 内容未变化的下一轮：静默，不再推送，也不再追加版本
        _, titles = self._run(changed)
        self.assertEqual(titles, [])
        self.assertEqual(len(storage.dyn_query("weibo", item_id="100")), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
