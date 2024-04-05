from typing import Any, Union

from qtpy.QtCore import QAbstractItemModel, QModelIndex, Qt
from qtpy.QtWidgets import QFileIconProvider

from copick.impl.tree import TreeRoot
from copick.models import CopickRoot


class QCoPickTreeModel(QAbstractItemModel):
    def __init__(
        self,
        root_item: CopickRoot,
        parent=None,
    ):
        super().__init__(parent)
        self._root = TreeRoot(root=root_item)

        self._icon_provider = QFileIconProvider()

    def index(self, row: int, column: int, parent=QModelIndex()) -> Union[QModelIndex, None]:
        if not self.hasIndex(row, column, parent):
            return None

        parentItem = self._root if not parent.isValid() else parent.internalPointer()

        childItem = parentItem.child(row)

        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return None

    def parent(self, index: QModelIndex) -> Union[QModelIndex, None]:
        if not index.isValid():
            return None

        childItem = index.internalPointer()
        parentItem = childItem.parent

        if parentItem != self._root:
            return self.createIndex(parentItem.childIndex(), 0, parentItem)
        else:
            return QModelIndex()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        parentItem = self._root if not parent.isValid() else parent.internalPointer()

        return parentItem.childCount()

    def columnCount(self, parent: QModelIndex = QModelIndex()):
        return self._root.columnCount()

    def data(self, index: QModelIndex, role: int = ...) -> Any:
        if not index.isValid():
            return None

        item = index.internalPointer()

        if role == 0:
            return item.data(index.column())

        if role == 1 and index.column() == 0:
            return self._icon_provider.icon(QFileIconProvider.IconType.Folder)
            # if item.is_dir:
            #
            # elif item.is_file:
            #     if item.being_fetched:
            #         app = QApplication.instance()
            #
            #         icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
            #         return icon
            #     elif item.is_cached:
            #         app = QApplication.instance()
            #
            #         icon = app.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
            #         return icon
            #     else:
            #         return self._icon_provider.icon(QFileIconProvider.IconType.File)
        else:
            return None

    def hasChildren(self, parent: QModelIndex = ...) -> bool:
        parentItem = self._root if not parent.isValid() else parent.internalPointer()

        return parentItem.is_dir

    def headerData(self, section, orientation, role=...):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section == 0:
                return "Name"
            elif section == 1:
                return "Size"

    def flags(self, index: QModelIndex) -> Union[Qt.ItemFlag, None]:
        if not index.isValid():
            return None

        index.internalPointer()

        # if item.is_dir:
        #     return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        #
        # if item.is_file:
        #     if item.extension in self._openable_types:
        #         return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        #     else:
        #         return Qt.ItemFlag.ItemIsSelectable
