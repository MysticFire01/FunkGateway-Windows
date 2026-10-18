from PySide6.QtWidgets import QPushButton, QMenu, QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLineEdit, QLabel
from PySide6.QtCore import Qt
import time

MUMBLE_EMOJI=("😀","😁","😂","🤣","😊","😉","😍","😎","👍","👋","❤️","🎉","🎙️","📻","⚓")
FRN_SMILEYS=(":)",":D",";)",":P",":(","^^","<3",":-)",":-D",";-)")


def emoji_button(entry, protocol="mumble", parent=None):
    btn=QPushButton("☺",parent)
    btn.setToolTip("Emoji auswählen" if protocol=="mumble" else "FRN-kompatiblen Smiley auswählen")
    menu=QMenu(btn)
    for symbol in (MUMBLE_EMOJI if protocol=="mumble" else FRN_SMILEYS):
        action=menu.addAction(symbol)
        action.triggered.connect(lambda checked=False, symbol=symbol: (entry.insert(symbol),entry.setFocus()))
    btn.setMenu(menu)
    return btn


class PrivateChatDialog(QDialog):
    def __init__(self, target, name, sender, protocol="mumble", parent=None):
        super().__init__(parent)
        self.target=target
        self.sender=sender
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        self.setWindowTitle(protocol.upper()+" – Privatnachricht: "+name)
        self.resize(520,400)
        layout=QVBoxLayout(self)
        self.history=QPlainTextEdit()
        self.history.setReadOnly(True)
        layout.addWidget(self.history,1)
        row=QHBoxLayout()
        self.entry=QLineEdit()
        self.entry.setPlaceholderText("Nachricht an "+name)
        self.entry.returnPressed.connect(self.send)
        row.addWidget(self.entry,1)
        row.addWidget(emoji_button(self.entry,protocol,self))
        button=QPushButton("Senden")
        button.clicked.connect(self.send)
        row.addWidget(button)
        layout.addLayout(row)
        self.status=QLabel("Zustellung serverabhängig.")
        layout.addWidget(self.status)

    def append_message(self, sender, message):
        self.history.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {sender}: {message}")

    def send(self):
        message=self.entry.text().strip()
        if not message:
            return
        try:
            self.sender(self.target,message)
        except Exception as exc:
            self.status.setText("Senden fehlgeschlagen: "+str(exc))
            return
        self.append_message("Ich",message)
        self.entry.clear()
        self.status.setText("An Server gesendet; Zustellung nicht bestätigt.")
