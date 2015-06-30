# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'panel_not_found_dialog.ui'
#
#      by: pyside-uic 0.2.13 running on PySide 1.1.1
#
# WARNING! All changes made in this file will be lost!

from tank.platform.qt import QtCore, QtGui

class Ui_PanelNotFoundDialog(object):
    def setupUi(self, PanelNotFoundDialog):
        PanelNotFoundDialog.setObjectName("PanelNotFoundDialog")
        PanelNotFoundDialog.resize(369, 587)
        self.gridLayout = QtGui.QGridLayout(PanelNotFoundDialog)
        self.gridLayout.setObjectName("gridLayout")
        spacerItem = QtGui.QSpacerItem(20, 175, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 0, 1, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(78, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 1, 0, 1, 1)
        self.verticalLayout = QtGui.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.label = QtGui.QLabel(PanelNotFoundDialog)
        self.label.setMinimumSize(QtCore.QSize(161, 161))
        self.label.setMaximumSize(QtCore.QSize(161, 161))
        self.label.setText("")
        self.label.setPixmap(QtGui.QPixmap(":/tk_nuke/not_found.png"))
        self.label.setScaledContents(True)
        self.label.setObjectName("label")
        self.verticalLayout.addWidget(self.label)
        self.message = QtGui.QLabel(PanelNotFoundDialog)
        self.message.setAlignment(QtCore.Qt.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setObjectName("message")
        self.verticalLayout.addWidget(self.message)
        self.gridLayout.addLayout(self.verticalLayout, 1, 1, 1, 1)
        spacerItem2 = QtGui.QSpacerItem(78, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem2, 1, 2, 1, 1)
        spacerItem3 = QtGui.QSpacerItem(20, 175, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem3, 2, 1, 1, 1)

        self.retranslateUi(PanelNotFoundDialog)
        QtCore.QMetaObject.connectSlotsByName(PanelNotFoundDialog)

    def retranslateUi(self, PanelNotFoundDialog):
        PanelNotFoundDialog.setWindowTitle(QtGui.QApplication.translate("PanelNotFoundDialog", "Shotgun Browser", None, QtGui.QApplication.UnicodeUTF8))
        self.message.setText(QtGui.QApplication.translate("PanelNotFoundDialog", "TextLabel", None, QtGui.QApplication.UnicodeUTF8))

from . import resources_rc
