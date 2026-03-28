# ─────────────────────────────────────────────
# Python versions of your C++ data structures
# ─────────────────────────────────────────────


class BSTNode:
    def __init__(self, flight_id, flight_obj=None):
        self.flight_id  = flight_id
        self.flight_obj = flight_obj   # Can hold a dict or Django model instance
        self.left  = None
        self.right = None


class RecordBST:
    """Binary Search Tree keyed on flight_id."""

    def __init__(self):
        self.root = None

    def insert(self, flight_id, flight_obj=None):
        node = BSTNode(flight_id, flight_obj)
        if self.root is None:
            self.root = node
            return
        current, parent = self.root, None
        while current:
            parent = current
            if flight_id < current.flight_id:
                current = current.left
            else:
                current = current.right
        if flight_id < parent.flight_id:
            parent.left = node
        else:
            parent.right = node

    def search(self, flight_id):
        current = self.root
        while current:
            if current.flight_id == flight_id:
                return True
            current = current.left if flight_id < current.flight_id else current.right
        return False

    def delete(self, value):
        parent, current = None, self.root
        while current and current.flight_id != value:
            parent = current
            current = current.left if value < current.flight_id else current.right
        if current is None:
            return False

        # No child
        if current.left is None and current.right is None:
            if current is self.root:
                self.root = None
            elif parent.left is current:
                parent.left = None
            else:
                parent.right = None

        # One child
        elif current.left is None or current.right is None:
            child = current.left if current.left else current.right
            if current is self.root:
                self.root = child
            elif parent.left is current:
                parent.left = child
            else:
                parent.right = child

        # Two children — in-order successor
        else:
            succ_parent, succ = current, current.right
            while succ.left:
                succ_parent, succ = succ, succ.left
            current.flight_id  = succ.flight_id
            current.flight_obj = succ.flight_obj
            if succ_parent.left is succ:
                succ_parent.left = succ.right
            else:
                succ_parent.right = succ.right
        return True

    def inorder(self, node=None, first_call=True):
        if first_call:
            node = self.root
        if node is None:
            return []
        return (
            self.inorder(node.left, False)
            + [node.flight_id]
            + self.inorder(node.right, False)
        )


class MinHeapQueue:
    """
    Min-Heap Priority Queue.
    Priority: emergency first, then earliest time.
    Mirrors your C++ Queue class.
    """

    def __init__(self):
        self._heap = []   # list of dicts: {flight_id, airline, status, time, emergency, runway_id}

    # ── helpers ──────────────────────────────
    @staticmethod
    def _parent(i): return (i - 1) // 2

    @staticmethod
    def _left(i): return 2 * i + 1

    @staticmethod
    def _right(i): return 2 * i + 2

    def _higher_priority(self, a, b):
        """Returns True if a should be served before b."""
        if a['emergency'] != b['emergency']:
            return a['emergency']           # emergency always first
        return a['time'] < b['time']        # earlier time wins

    def _swap(self, i, j):
        self._heap[i], self._heap[j] = self._heap[j], self._heap[i]

    def _heapify_up(self, index):
        while index > 0:
            p = self._parent(index)
            if self._higher_priority(self._heap[index], self._heap[p]):
                self._swap(index, p)
                index = p
            else:
                break

    def _heapify_down(self, index):
        n = len(self._heap)
        while True:
            smallest = index
            l, r = self._left(index), self._right(index)
            if l < n and self._higher_priority(self._heap[l], self._heap[smallest]):
                smallest = l
            if r < n and self._higher_priority(self._heap[r], self._heap[smallest]):
                smallest = r
            if smallest != index:
                self._swap(index, smallest)
                index = smallest
            else:
                break

    # ── public API ───────────────────────────
    def enqueue(self, flight_dict):
        self._heap.append(flight_dict)
        self._heapify_up(len(self._heap) - 1)

    def dequeue(self):
        if not self._heap:
            return None
        top = self._heap[0]
        self._heap[0] = self._heap[-1]
        self._heap.pop()
        if self._heap:
            self._heapify_down(0)
        return top

    def peek(self):
        return self._heap[0] if self._heap else None

    def is_empty(self):
        return len(self._heap) == 0

    def remove_by_id(self, flight_id):
        """Remove any flight by ID (linear scan + re-heapify)."""
        for i, f in enumerate(self._heap):
            if f['flight_id'] == flight_id:
                self._heap[i] = self._heap[-1]
                self._heap.pop()
                if i < len(self._heap):
                    self._heapify_up(i)
                    self._heapify_down(i)
                return True
        return False

    def to_list(self):
        """Sorted snapshot for display."""
        import heapq
        return sorted(
            self._heap,
            key=lambda f: (not f['emergency'], f['time'])
        )

    def size(self):
        return len(self._heap)
