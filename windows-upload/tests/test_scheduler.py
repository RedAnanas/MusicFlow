"""并发调度的停止、卡住和检查点恢复；仅用假进程和假上传器。"""
from pathlib import Path
import tempfile
import os
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import scheduler


class SchedulerTests(unittest.TestCase):
    def test_并发大于一才启用预计算且不超过任务名额(self):
        for concurrency in (1, 2, 5):
            with self.subTest(concurrency=concurrency), tempfile.TemporaryDirectory() as directory:
                worker = Mock()
                worker.binding = {'account_scope': 'scope'}
                worker.readiness.return_value = dict(authorization_saved=True, client_exited=True, compatible=True, context_matches=True)
                jobs = [{'job_id': str(index)} for index in range(concurrency)]
                worker.json_request.side_effect = [{'concurrency': concurrency, 'jobs': []}] + [{'job': job} for job in jobs]
                with patch.object(scheduler, 'PRIVATE', Path(directory)):
                    runner = scheduler.UploadScheduler(worker, Mock())
                    runner.spawn = Mock(side_effect=lambda job: runner.processes.update({job['job_id']: {}}))
                    runner.tick()
                self.assertEqual(runner.spawn.call_count, concurrency)
                self.assertTrue(all(job['precompute_fingerprints'] == (concurrency > 1) for job in jobs))

    def test_心跳不能替代进展且正常等待不误判(self):
        self.assertFalse(scheduler.stalled({'stage':'signature','last_progress_at':0}, 179))
        self.assertTrue(scheduler.stalled({'stage':'signature','last_progress_at':0}, 181))
        self.assertTrue(scheduler.stalled({'stage':'audio','last_progress_at':0}, 121))
        self.assertFalse(scheduler.stalled({'stage':'session-wait','last_progress_at':0}, 3600))
        self.assertFalse(scheduler.stalled({'last_progress_at':0,'wait_until':1000}, 999))
        self.assertFalse(scheduler.stalled({'stage':'waiting','wait_seconds':600,'wait_until':1000}, 999))
        self.assertTrue(scheduler.stalled({'stage':'waiting','wait_seconds':600,'wait_until':1000}, 1031))
        self.assertFalse(scheduler.stalled({'stage':'signature','last_progress_at':1050,'wait_seconds':600}, 1100))
        self.assertFalse(scheduler.stalled({'stage':'signature','last_progress_at':990}, 1052))

    def test_进程未退出不释放名额且降并发不杀在途任务(self):
        worker = Mock()
        ready = dict(authorization_saved=True,client_exited=True,compatible=True,context_matches=True)
        worker.readiness.return_value=ready
        worker.load.return_value={'monitor':{'last_progress_at':1000}}
        worker.json_request.return_value={'concurrency':1,'jobs':[{'id':'a','stop_requested':False,'state':'uploading'}]}
        process=Mock()
        process.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory, patch.object(scheduler,'PRIVATE',Path(directory)), patch.object(scheduler.time,'time',return_value=1000):
            runner=scheduler.UploadScheduler(worker,Mock())
            runner.processes={'a':{'process':process,'stop_at':None,'reason':'worker_interrupted','started_at':1000}}
            runner.finish=Mock()
            runner.spawn=Mock()
            self.assertFalse(runner.tick())
            runner.finish.assert_not_called()
            runner.spawn.assert_not_called()
            process.wait.assert_not_called()

    def test_停止先通知超时再终止退出后才收尾(self):
        worker=Mock()
        worker.readiness.return_value={}
        job={'id':'a','stop_requested':True,'state':'stopping'}
        worker.json_request.return_value={'concurrency':1,'jobs':[job]}
        worker.load.return_value={}
        process=Mock()
        process.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory, patch.object(scheduler,'PRIVATE',Path(directory)):
            runner=scheduler.UploadScheduler(worker,Mock())
            runner.processes={'a':{'process':process,'stop_at':None,'reason':'worker_interrupted','started_at':1000}}
            runner.finish=Mock()
            runner.terminate=Mock()
            with patch.object(scheduler.time,'monotonic',return_value=100):
                runner.tick()
            self.assertTrue((Path(directory)/'a.stop').exists())
            runner.terminate.assert_not_called()
            with patch.object(scheduler.time,'monotonic',return_value=146):
                runner.tick()
            runner.terminate.assert_called_once_with(process)
            runner.finish.assert_not_called()
            process.poll.return_value=0
            runner.tick()
            runner.finish.assert_called_once_with(job,'worker_interrupted')
            self.assertFalse(runner.processes)

    def test_授权暂停排空后退出且不领取任务(self):
        worker=Mock()
        worker.readiness.return_value={}
        worker.json_request.return_value={'concurrency':5,'jobs':[]}
        with tempfile.TemporaryDirectory() as directory, patch.object(scheduler,'PRIVATE',Path(directory)):
            (Path(directory)/'.pause-for-authorization').touch()
            runner=scheduler.UploadScheduler(worker,Mock())
            self.assertTrue(runner.tick())
            self.assertEqual(worker.json_request.call_count,1)

    def test_明确未发请求可恢复但不确定请求必须核对(self):
        worker=Mock()
        job={'id':'a','sha256':'abc','attempt':0,'stop_requested':True}
        with tempfile.TemporaryDirectory() as directory, patch.object(scheduler,'PRIVATE',Path(directory)):
            (Path(directory)/'a.dpapi').touch()
            worker.load.return_value={'apple_started':True,'request_started':False}
            result,_=scheduler.interrupted_result(worker,job,'worker_interrupted')
            self.assertEqual(result['state'],'stopped')
            self.assertEqual(result['action'],'upload')
            worker.load.return_value={'apple_started':True,'request_started':True}
            result,_=scheduler.interrupted_result(worker,job,'worker_interrupted')
            self.assertEqual(result['state'],'requires_review')

    def test_已持久化完成结果优先于停止(self):
        worker=Mock()
        job={'id':'a','sha256':'abc','attempt':0,'stop_requested':True}
        final={'state':'cloud_completed','evidence':{'all_work_completed':True}}
        with tempfile.TemporaryDirectory() as directory, patch.object(scheduler,'PRIVATE',Path(directory)):
            (Path(directory)/'a.dpapi').touch()
            worker.load.return_value={'attempt':0,'final_event':final}
            result,_=scheduler.interrupted_result(worker,job,'worker_interrupted')
            self.assertEqual(result,final)

    def test_启动失败暂停补领且不循环创建进程(self):
        worker=Mock()
        worker.binding={'account_scope':'scope'}
        worker.readiness.return_value=dict(authorization_saved=True,client_exited=True,compatible=True,context_matches=True)
        worker.json_request.side_effect=[{'concurrency':5,'jobs':[]},{'job':{'job_id':'a'}}]
        with tempfile.TemporaryDirectory() as directory, patch.object(scheduler,'PRIVATE',Path(directory)):
            runner=scheduler.UploadScheduler(worker,Mock())
            runner.spawn=Mock(side_effect=OSError('resource'))
            runner.tick()
            self.assertTrue(runner.blocked)
            runner.spawn.assert_called_once()


@unittest.skipIf(os.name == 'nt', 'Linux 进程组及文件描述符继承')
class SchedulerProcessTests(unittest.TestCase):
    def test_五个真实任务进程隔离且可以独立终止(self):
        from runtime import exclusive_lock
        import runtime
        worker = Mock()
        worker.ffmpeg = Path('/fake/ffmpeg')
        worker.target = Path('/fake/agent')
        real_popen = subprocess.Popen
        command = "import json,sys,time; job=json.load(sys.stdin); print(job['job_id'], flush=True); time.sleep(30)"

        def spawn_fake_task(args, **kwargs):
            return real_popen([sys.executable, '-c', command], **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(runtime, 'PRIVATE', directory), patch.object(scheduler, 'PRIVATE', directory):
                with exclusive_lock() as lock:
                    runner = scheduler.UploadScheduler(worker, lock)
                    try:
                        with patch.object(scheduler.subprocess, 'Popen', side_effect=spawn_fake_task):
                            for index in range(5):
                                runner.spawn({'job_id': str(index)})
                        processes = [entry['process'] for entry in runner.processes.values()]
                        self.assertEqual(len({process.pid for process in processes}), 5)
                        self.assertTrue(all(process.poll() is None for process in processes))
                        runner.terminate(processes[0])
                        self.assertIsNotNone(processes[0].poll())
                        self.assertTrue(all(process.poll() is None for process in processes[1:]))
                    finally:
                        for entry in runner.processes.values():
                            runner.terminate(entry['process'])


if __name__=='__main__':
    unittest.main()
