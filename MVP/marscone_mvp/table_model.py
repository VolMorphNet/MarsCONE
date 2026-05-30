"""Qt table model backed by a pandas DataFrame."""

from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class DataFrameTableModel(QAbstractTableModel):
    """Expose DataFrame rows and columns for Qt table views."""

    def __init__(
        self,
        dataframe: pd.DataFrame | None = None,
        float_precision: int | None = None,
    ) -> None:
        super().__init__()
        self._dataframe = dataframe if dataframe is not None else pd.DataFrame()
        self._float_precision = float_precision

    @staticmethod
    def _display_column_name(column_name: object) -> str:
        if str(column_name) == "volume":
            return "volume (km^3)"
        return str(column_name)

    @staticmethod
    def _display_value(column_name: object, value: object) -> object:
        if str(column_name) == "volume" and pd.notna(value):
            try:
                return float(value) / 1_000_000_000.0
            except (TypeError, ValueError):
                return value
        return value

    def set_dataframe(self, dataframe: pd.DataFrame) -> None:
        """Replace the model data with a new DataFrame and reset the view."""
        self.beginResetModel()
        self._dataframe = dataframe
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._dataframe.index)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._dataframe.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        column_name = self._dataframe.columns[index.column()]
        value = self._display_value(column_name, self._dataframe.iat[index.row(), index.column()])
        if (
            self._float_precision is not None
            and isinstance(value, float)
            and not pd.isna(value)
        ):
            return f"{value:.{self._float_precision}f}"
        return "" if pd.isna(value) else str(value)

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        if self._dataframe.empty or column >= len(self._dataframe.columns):
            return

        column_name = self._dataframe.columns[column]
        ascending = order == Qt.AscendingOrder

        self.layoutAboutToBeChanged.emit()
        self._dataframe.sort_values(
            by=column_name,
            ascending=ascending,
            inplace=True,
            na_position="last",
            kind="mergesort",
        )
        self._dataframe.reset_index(drop=True, inplace=True)
        self.layoutChanged.emit()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if section < len(self._dataframe.columns):
                return self._display_column_name(self._dataframe.columns[section])
            return None
        return str(section + 1)
