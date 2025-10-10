from collections import defaultdict
import time
from typing import Dict, List, Optional
from push import global_config as config


class Scheduler:
    def __init__(self):
        self.items: Dict[Dict] = {}
        self.total_weight = 0
        self.access_times = defaultdict(list)
        self.avg_interval = defaultdict(int)

    def update(self, key: str, new_weight: int) -> None:
        """更新权重"""
        if config.get("scheduler", "enable") != "true":
            new_weight = 1
        else:
            max_weight = int(config.get("scheduler", "max_weight") or 10)
        new_weight = max(1, min(new_weight, max_weight))
        self.total_weight += new_weight - self.items[key]["weight"]
        self.items[key]["weight"] = new_weight

    def next_target(self) -> Optional[str]:
        """获取下一个要访问的项目"""
        if not self.items:
            return None

        # 平滑加权轮询算法
        best_item = None
        max_current_weight = -1

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
        new_set = set(new_ids)
        old_set = set(self.items.keys())

        # 新增
        for key in new_set - old_set:
            self.items[key] = {
                "weight": 100,  # 权重不能为负数
                "current_weight": 0,
            }
            self.total_weight += 100

        # 删除
        for key in old_set - new_set:
            self.total_weight -= self.items[key]["weight"]
            del self.items[key]
