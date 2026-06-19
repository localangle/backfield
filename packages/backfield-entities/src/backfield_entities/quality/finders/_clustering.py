"""Union-find helpers for grouping duplicate pairs into clusters."""

from __future__ import annotations


class UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, node: str) -> None:
        if node not in self._parent:
            self._parent[node] = node

    def find(self, node: str) -> str:
        parent = self._parent.get(node, node)
        if parent != node:
            self._parent[node] = self.find(parent)
            return self._parent[node]
        self._parent[node] = node
        return node

    def union(self, a: str, b: str) -> None:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a

    def clusters(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for node in self._parent:
            root = self.find(node)
            grouped.setdefault(root, []).append(node)
        for members in grouped.values():
            members.sort()
        return grouped


def cluster_ids_from_pairs(pairs: list[tuple[str, str]]) -> list[list[str]]:
    uf = UnionFind()
    for a_id, b_id in pairs:
        uf.add(a_id)
        uf.add(b_id)
        uf.union(a_id, b_id)
    clusters = [sorted(members) for members in uf.clusters().values() if len(members) >= 2]
    clusters.sort(key=lambda members: (-len(members), members[0]))
    return clusters
