"""
_lookup_worker.py — 后台词典查询。

职责单一：在独立 QThread 中执行词典查询，通过信号返回结果给主线程。
不含取词、UI、防抖逻辑（由调用方控制）。
"""

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from quickdict.dict_engine import DictEngine


class LookupWorker(QObject):
    """后台词典查询工作器，需配合 QThread.moveToThread 使用。"""

    sig_result = pyqtSignal(str, object)  # (word, data_dict | None)

    def __init__(self, db_path: str):
        super().__init__()
        self._db_path = db_path
        self._engine: DictEngine | None = None

    @pyqtSlot()
    def init_engine(self):
        """在工作线程中初始化词典引擎（sqlite3 连接必须在使用线程创建）。"""
        self._engine = DictEngine(self._db_path)
        # 预热首查路径，减少第一次 lookup 的初始化开销。
        try:
            self._engine.lookup("the")
        except Exception:
            pass

    def lookup(self, word: str, fallback_parts):
        """
        查询单词，失败时依次尝试拆分词。

        结果通过 sig_result 信号发送: (原始单词, 查询结果或None)。
        """
        if not self._engine:
            return
        data = self._engine.lookup(word)
        if not data:
            for part in fallback_parts:
                data = self._engine.lookup(part)
                if data:
                    break
        self.sig_result.emit(word, data)

    @pyqtSlot()
    def cleanup(self):
        """关闭引擎资源（应在工作线程中调用）。"""
        if self._engine:
            self._engine.close()
            self._engine = None
