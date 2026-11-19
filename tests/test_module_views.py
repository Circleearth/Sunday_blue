from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
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
        self.assertEqual(self.window.page_stack.count(),10)
        self.assertTrue(hasattr(self.window,"relationship_button"))
        self.assertEqual(self.config.value['main_page'],'focus')
        page=self.pages['FocusPage'];clock=[0];self.hub.focus.clock=lambda:clock[0]
        page.begin();self.assertEqual(self.hub.focus.status()['state'],'running');self.assertFalse(page.start.isEnabled())
        for _ in range(25):clock[0]+=5;self.hub.focus.checkpoint()
        page.toggle();self.assertEqual(self.hub.focus.status()['state'],'paused')
        with patch.object(QMessageBox,'information') as result:page.settle()
        self.assertTrue(result.called);self.assertEqual(self.hub.rewards.balances()['coins'],0)
        self.assertEqual(self.hub.focus.last_settlement['work_points'],2)
        self.assertEqual(page.records.count(),1)
        self.window.module_navigation.button(0).click();self.assertIs(self.window.page_stack.currentWidget(),self.window.chat_page)
    def test_focus_page_restores_persisted_activity_fields_and_draft_preserved(self):
        page=self.pages['FocusPage'];clock=[0];self.hub.focus.clock=lambda:clock[0]
        # start with a non-default category/label/role and run a valid duration
        self.hub.focus.start('学习','写作业','red')
        for _ in range(25):clock[0]+=5;self.hub.focus.checkpoint()
        state=self.hub.focus.status()
        self.assertEqual(state['state'],'running');self.assertEqual(state['category'],'学习')
        self.assertEqual(state['label'],'写作业');self.assertEqual(state['role_id'],'red')
        # rebuild the page (as hub refresh would) -> running fields must show actual values
        page.refresh()
        self.assertEqual(page.category.currentText(),'学习')
        self.assertEqual(page.label.text(),'写作业')
        self.assertEqual(page.roles.currentData(),'red')
        self.assertFalse(page.start.isEnabled());self.assertTrue(page.pause.isEnabled())
        # pause: clock must not grow, and refresh must NOT overwrite idle-like fields
        page.toggle();self.assertEqual(self.hub.focus.status()['state'],'paused')
        before=self.hub.focus.status()['elapsed']
        clock[0]+=1000;page.refresh();self.assertEqual(self.hub.focus.status()['elapsed'],before)
        self.assertEqual(page.category.currentText(),'学习');self.assertEqual(page.label.text(),'写作业')
        # finish -> settled exactly once; balance must not double on a second settle click
        with patch.object(QMessageBox,'information'):page.settle()
        balance=self.hub.rewards.balances()['coins']
        self.assertEqual(self.hub.focus.status()['state'],'idle')
        with patch.object(QMessageBox,'information'):page.settle()
        self.assertEqual(self.hub.rewards.balances()['coins'],balance)
        # settle only fired once: no second activity record for the same run
        self.assertEqual(len(self.hub.focus.records()),1)
        # back to idle: user's fresh draft category must survive a refresh
        page.category.setEditText('运动');page.label.setText('跑步')
        page.refresh();self.assertEqual(page.category.currentText(),'运动')
        self.assertEqual(page.label.text(),'跑步')

    def test_group_controls_keep_draft_and_route_real_service(self):
        gid=self.hub.social.create_group('测试会议',['rui','mia'])
        gid2=self.hub.social.create_group('隔离测试群',['red'])
        page=self.pages['SocialPage'];page.refresh();page.input.setPlainText('未发送的草稿')
        self.hub.changed.emit('modules');self.assertEqual(page.input.toPlainText(),'未发送的草稿')
        # 两个隔离群切换草稿不丢：切到第二群恢复它自己的草稿，切回来仍保留
        page.groups.setCurrentIndex(page.groups.findData(gid2))
        self.assertEqual(page.input.toPlainText(),'')
        page.input.setPlainText('第二群的草稿')
        page.groups.setCurrentIndex(page.groups.findData(gid))
        self.assertEqual(page.input.toPlainText(),'未发送的草稿')
        page.groups.setCurrentIndex(page.groups.findData(gid2))
        self.assertEqual(page.input.toPlainText(),'第二群的草稿')
        page.groups.setCurrentIndex(page.groups.findData(gid))
        with patch.object(self.hub,'send_group') as send:page.post();send.assert_called_once_with(gid,'未发送的草稿')
        self.assertEqual(page.input.toPlainText(),'')
        page.memory.setChecked(False);self.assertFalse(self.hub.social.group(gid)['private_context'])
        self.hub.jobs[gid]=object();page.refresh();self.assertFalse(page.send.isEnabled());self.assertTrue(page.stop.isEnabled());self.hub.jobs.clear()
        # 记忆支撑状态按当前群成员过滤：第二群没有 rui/mia，不应显示他们的状态
        self.hub.social.memory_status={'rui':'最近私聊 1 条','mia':'最近私聊 0 条'}
        page.groups.setCurrentIndex(page.groups.findData(gid2));page.refresh()
        self.assertNotIn('最近私聊 1 条',page.state.text())
        page.groups.setCurrentIndex(page.groups.findData(gid));page.refresh()
        self.assertIn('Rui',page.state.text())
        # 发送者名称取历史快照，改名后仍显示旧名
        self.hub.social.post(gid,'角色说过的话','rui','旧名','assistant')
        from sunday_blue.roles import RoleRegistry
        RoleRegistry(self.hub.root).update('rui',name='Rui改')
        page.refresh()
        html=page.messages.toHtml()
        self.assertIn('旧名',html)          # 历史快照名保留
        self.assertNotIn('Rui改',html)     # 不受角色改名破坏
        RoleRegistry(self.hub.root).update('rui',name='Rui')
    def test_redeem_cancel_keeps_coins_and_gift_target_shown(self):
        page=self.pages['RewardsPage']
        with self.hub.db.connect() as db:db.execute("INSERT INTO coin_ledger VALUES('seed',100,'test','now')")
        gid=page.invoke(lambda:self.hub.rewards.add('送小礼物',10,'gift',0,0,'mia'))
        before=self.hub.rewards.balances()['coins']
        # select the gift reward, then CANCEL the confirmation dialog -> coins unchanged, no redemption row
        page.refresh()
        self.assertTrue(any('送给 Mia' in page.items.item(i).text() for i in range(page.items.count())),
                        'gift target role name must be displayed on the reward card')
        page.items.setCurrentRow(0)
        for i in range(page.items.count()):
            if page.items.item(i).data(Qt.ItemDataRole.UserRole)['id']==gid:page.items.setCurrentRow(i);break
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):page.redeem()
        self.assertEqual(self.hub.rewards.balances()['coins'],before)
        self.assertEqual(len(self.hub.rewards.history()),0)  # no redemption created on cancel
        # now actually redeem -> coins deducted exactly once, history records the gift target
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):page.redeem()
        self.assertEqual(self.hub.rewards.balances()['coins'],before-10)
        record=self.hub.rewards.history()[0]
        self.assertEqual(record['role_id'],'mia');self.assertEqual(record['kind'],'gift')
        self.assertTrue(any('送给 Mia' in page.history.item(i).text() for i in range(page.history.count())),
                        'gift target role name must be displayed in redemption history')
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
