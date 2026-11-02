"""Different requests cannot reserve the same chapter concurrently."""
import concurrent.futures
import test_job_plans as fixtures
from api.job_plans import preview,confirm
from api.books import BookError
from api.job_control import stop,resume

class ConflictTests(fixtures.PlanTests):
    test_snapshot_kept_after_config_changes_and_confirm_repeated=None
    test_changed_bytes_blocks_confirm_and_unavailable_action_rejected=None
    def test_concurrent_confirm_and_resume_reservation(self):
        plans=[preview(self.repo,self.request(),True) for _ in range(2)]
        def attempt(plan):
            try:return confirm(self.repo,plan['id'])['status']
            except BookError as exc:return exc.status
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(attempt,plans))
        self.assertEqual(sorted(map(str,results)),['409','queued'])
        winner=plans[results.index('queued')]['id'];loser=plans[results.index(409)]['id']
        stop(self.repo,winner);self.assertEqual(confirm(self.repo,loser)['status'],'queued')
        with self.assertRaises(BookError):resume(self.repo,winner)
        stop(self.repo,loser);self.assertEqual(resume(self.repo,winner)['status'],'queued')
