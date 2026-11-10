from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox,QDialog
from sunday_blue.storage import Config
from sunday_blue.ui import MainWindow
from sunday_blue.modules.workspace import install_workspace
from sunday_blue.model_preferences import RoleModelDialog

ROOT=Path(__file__).resolve().parents[1]
APP=QApplication.instance() or QApplication([])


class ModuleViewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='sunday-test-')
        self.config=Config(self.temp.name);self.window=MainWindow(self.config)
        self.hub=install_workspace(self.window);self.hub.timer.stop()
        self.pages={self.window.page_stack.widget(i).__class__.__name__:self.window.page_stack.widget(i) for i in range(1,self.window.page_stack.count())}
    def tearDown(self):
        for job in self.hub.jobs.values():job.cancel.set();job.wait(5000)
        APP.processEvents();self.window.close();self.window.deleteLater();APP.processEvents();self.temp.cleanup()
    def test_navigation_focus_settlement_and_persistence(self):
        self.assertEqual(self.window.page_stack.count(),5)
        self.assertEqual(self.config.value['main_page'],'focus')
        page=self.pages['FocusPage'];clock=[0];self.hub.focus.clock=lambda:clock[0]
        page.begin();self.assertEqual(self.hub.focus.status()['state'],'running');self.assertFalse(page.start.isEnabled())
        for _ in range(25):clock[0]+=5;self.hub.focus.checkpoint()
        page.toggle();self.assertEqual(self.hub.focus.status()['state'],'paused')
        with patch.object(QMessageBox,'information') as result:page.settle()
        self.assertTrue(result.called);self.assertEqual(self.hub.rewards.balances()['coins'],2)
        self.assertEqual(page.records.count(),1)
        self.window.module_navigation.button(0).click();self.assertIs(self.window.page_stack.currentWidget(),self.window.chat_page)
    def test_group_controls_keep_draft_and_route_real_service(self):
        gid=self.hub.social.create_group('测试会议',['rui','mia'])
        page=self.pages['SocialPage'];page.refresh();page.input.setPlainText('未发送的草稿')
        self.hub.changed.emit('modules');self.assertEqual(page.input.toPlainText(),'未发送的草稿')
        with patch.object(self.hub,'send_group') as send:page.post();send.assert_called_once_with(gid,'未发送的草稿')
        self.assertEqual(page.input.toPlainText(),'')
        page.memory.setChecked(False);self.assertFalse(self.hub.social.group(gid)['private_context'])
        self.hub.jobs[gid]=object();page.refresh();self.assertFalse(page.send.isEnabled());self.assertTrue(page.stop.isEnabled());self.hub.jobs.clear()
    def test_budget_confirmation_not_triggered_by_opening_page(self):
        with self.hub.db.connect() as db:db.execute("INSERT INTO coin_ledger VALUES('seed',50,'test','now')")
        rid=self.hub.rewards.add('预算奖励',10,'budget',cents=100)
        record=self.hub.rewards.redeem(rid,'request');self.hub.rewards.adjust_budget(1000,'测试','budget')
        page=self.pages['RewardsPage'];page.refresh();page.history.setCurrentRow(0)
        self.assertEqual(self.hub.rewards.balances()['budget_cents'],1000)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):page.confirm()
        self.assertEqual(self.hub.rewards.balances()['budget_cents'],1000)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):page.confirm()
        self.assertEqual(self.hub.rewards.balances()['budget_cents'],900)
    def test_role_model_draft_preserves_other_roles_and_global_key(self):
        original=self.config.snapshot()
        dialog=RoleModelDialog(self.config.root,original,'rui',self.window)
        dialog.enabled.setChecked(True);dialog.model.setText('strong-test');dialog.light.setText('light-test');dialog.save()
        self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.profile['model'],'strong-test')
        self.assertEqual(self.config.value['api'],original['api'])
        self.assertNotIn('model_profile',self.config.value['roles']['mia'])
        dialog.deleteLater();APP.processEvents()
