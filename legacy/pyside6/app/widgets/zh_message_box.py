"""中文按钮的消息框，避免系统显示 OK、Cancel 等英文。"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def zh_information(parent: QWidget | None, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Information)
    box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def zh_warning(parent: QWidget | None, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning)
    box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def zh_critical(parent: QWidget | None, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Critical)
    box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def zh_question_yes_no(
    parent: QWidget | None, title: str, text: str, *, default_no: bool = True
) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Question)
    yes_btn = box.addButton("是", QMessageBox.ButtonRole.YesRole)
    no_btn = box.addButton("否", QMessageBox.ButtonRole.NoRole)
    if default_no:
        box.setDefaultButton(no_btn)
    else:
        box.setDefaultButton(yes_btn)
    box.exec()
    return box.clickedButton() == yes_btn
