# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'dialog.ui'
#
# Created: Fri Jul 13 11:05:04 2012
#      by: pyside-uic 0.2.13 running on PySide 1.1.0
#
# WARNING! All changes made in this file will be lost!

from PySide import QtCore, QtGui

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(731, 485)
        self.horizontalLayout = QtGui.QHBoxLayout(Dialog)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.browser = ContextBrowserWidget(Dialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.browser.sizePolicy().hasHeightForWidth())
        self.browser.setSizePolicy(sizePolicy)
        self.browser.setMinimumSize(QtCore.QSize(380, 0))
        self.browser.setObjectName("browser")
        self.horizontalLayout.addWidget(self.browser)
        self.verticalLayout = QtGui.QVBoxLayout()
        self.verticalLayout.setSpacing(5)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label = QtGui.QLabel(Dialog)
        self.label.setText("")
        self.label.setPixmap(QtGui.QPixmap(":/res/tank_logo.png"))
        self.label.setObjectName("label")
        self.verticalLayout.addWidget(self.label)
        self.jump_to_fs = QtGui.QPushButton(Dialog)
        self.jump_to_fs.setObjectName("jump_to_fs")
        self.verticalLayout.addWidget(self.jump_to_fs)
        self.platform_docs = QtGui.QPushButton(Dialog)
        self.platform_docs.setObjectName("platform_docs")
        self.verticalLayout.addWidget(self.platform_docs)
        self.support = QtGui.QPushButton(Dialog)
        self.support.setObjectName("support")
        self.verticalLayout.addWidget(self.support)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.close = QtGui.QPushButton(Dialog)
        self.close.setObjectName("close")
        self.verticalLayout.addWidget(self.close)
        self.horizontalLayout.addLayout(self.verticalLayout)

        self.retranslateUi(Dialog)
        QtCore.QObject.connect(self.close, QtCore.SIGNAL("clicked()"), Dialog.accept)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QtGui.QApplication.translate("Dialog", "Your Current Context", None, QtGui.QApplication.UnicodeUTF8))
        self.jump_to_fs.setText(QtGui.QApplication.translate("Dialog", "Jump to the File System", None, QtGui.QApplication.UnicodeUTF8))
        self.platform_docs.setText(QtGui.QApplication.translate("Dialog", "Platform Documentation", None, QtGui.QApplication.UnicodeUTF8))
        self.support.setText(QtGui.QApplication.translate("Dialog", "Help Desk and Support", None, QtGui.QApplication.UnicodeUTF8))
        self.close.setText(QtGui.QApplication.translate("Dialog", "Close", None, QtGui.QApplication.UnicodeUTF8))

from ..context_browser import ContextBrowserWidget
from . import resources_rc
