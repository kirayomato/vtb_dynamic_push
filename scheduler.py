from collections import defaultdict
import time
import threading
from typing import Dict, List, Optional
from push import global_config as config
from math import sqrt


class Scheduler:
    def __init__(self, name: Optional[str] = None):
        # name: 调度器名称（weibo / bili_dy），用于区分各平台独立的静态权重配置
        self.name = name
        self.items: Dict[Dict] = {}
        self.total_weight = 0
        self.access_times = defaultdict(list)
        self.avg_interval = defaultdict(int)
        self.lock = threading.Lock()

    def static_weights(self) -> Dict[str, float]:
        """解析 [scheduler] 中与本调度器对应的 static_weight_{name} 配置，返回 uid -> 固定权重映射。"""
        if not self.name:
            return {}
        raw = config.get("scheduler", f"static_weight_{self.name}") or ""
        result: Dict[str, float] = {}
        if not raw:
            return result
        for part in raw.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            uid, _, w = part.partition(":")
            try:
                uid = uid.strip()
                val = float(w.strip())
                if val > 0:
                    result[uid] = val
            except ValueError:
                continue
        return result

    def update(self, key: str, new_weight: int) -> None:
        """更新权重（支持静态固定权重：被固定的目标权重不会被自动调整）"""
        with self.lock:
            old_weight = self.items[key]["weight"]
        static = self.static_weights()
        if key in static:
            # 手动固定权重，无视自动计算结果
            new_weight = static[key]
        elif config.get("scheduler", "enable") != "true":
            new_weight = 1
        else:
            max_weight = int(config.get("scheduler", "max_weight") or 10)
            new_weight = sqrt(new_weight)
            new_weight = max(1, min(new_weight, max_weight))
            new_weight = 0.2 * new_weight + 0.8 * old_weight
        self.total_weight += new_weight - old_weight
        self.items[key]["weight"] = new_weight

    def next_target(self) -> Optional[str]:
        """获取下一个要访问的项目"""
        with self.lock:
            if not self.items:
                return None

        # 平滑加权轮询算法
        best_item = None
        max_current_weight = -float("inf")

        # 第一步：增加当前权重
        for key, item in self.items.items():
            item["current_weight"] += item["weight"]
            if item["current_weight"] > max_current_weight:
                max_current_weight = item["current_weight"]
                best_item = key

        # 第二步：选中最大当前权重的项目，并减少其当前权重
        if best_item:
            self.items[best_item]["current_weight"] -= self.total_weight
            self.access_times[best_item].append(time.time())
            if len(self.access_times[best_item]) > 1:  #
                intervals = [
                    self.access_times[best_item][j]
                    - self.access_times[best_item][j - 1]
                    for j in range(1, len(self.access_times[best_item]))
                ]
                self.avg_interval[best_item] = (
                    sum(intervals) / len(intervals),
                    self.items[best_item]["weight"],
                )
            return best_item

        return None

    def update_targets(self, new_ids: List[str]):
        """更新目标列表：新增/删除目标"""
        with self.lock:
            new_set = set(new_ids)
            old_set = set(self.items.keys())

        max_weight = int(config.get("scheduler", "max_weight") or 10)
        static = self.static_weights()
        # 新增
        for key in new_set - old_set:
            weight = static.get(key, max_weight)
            self.items[key] = {
                "weight": weight,
                "current_weight": 100,
            }
            self.total_weight += weight

        # 删除
        for key in old_set - new_set:
            self.total_weight -= self.items[key]["weight"]
            del self.items[key]

    def get_info(self) -> dict:
        """返回当前调度器状态的序列化快照（线程安全）"""
        with self.lock:
            static = self.static_weights()
            targets = []
            for key, item in self.items.items():
                times = self.access_times.get(key, [])
                last_access = max(times) if times else None
                avg = self.avg_interval.get(key)
                targets.append(
                    {
                        "key": key,
                        "weight": round(item["weight"], 3),
                        "current_weight": round(item["current_weight"], 3),
                        "access_count": len(times),
                        "last_access": last_access,
                        "avg_interval": round(avg[0], 2) if avg else None,
                        "static": key in static,
                        "static_weight": static.get(key),
                    }
                )
            return {
                "total_weight": round(self.total_weight, 3),
                "target_count": len(self.items),
                "targets": targets,
            }
