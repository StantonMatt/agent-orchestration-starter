"""Compute-pool fixture parsing, policy gates and bounded SSH; no real remote calls."""
from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/compute_pool.py'
spec = importlib.util.spec_from_file_location('compute_pool', SCRIPT)
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)

LINUX_MEMORY = '''MemTotal:       65011712 kB
MemFree:         1048576 kB
MemAvailable:   16777216 kB
SwapTotal:       8388608 kB
SwapFree:        6291456 kB
'''
LINUX_PRESSURE = '''some avg10=1.25 avg60=2.50 avg300=3.00 total=12345
full avg10=0.00 avg60=0.01 avg300=0.02 total=123
'''
MAC_MEMORY = '''Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                              65536.
Pages active:                            20000.
Pages inactive:                         458752.
Pages speculative:                       65536.
Pages occupied by compressor:            40000.
'''
MAC_SWAP = 'vm.swapusage: total = 2048.00M  used = 512.00M  free = 1536.00M (encrypted)'


def reading(**overrides):
    values = dict(reachable=True, system='Linux', cores=32, total_memory_gib=62,
                  available_memory_gib=24, memory_pressure=0, memory_pressure_kind='psi_some_avg60',
                  swap_used_fraction=0.1, load_per_core=0.25, free_disk_gib=100,
                  on_ac_power=None, user_idle_seconds=None)
    values.update(overrides)
    return values


class ComputePoolTest(unittest.TestCase):
    def test_shipped_config_has_no_hosts(self):
        self.assertEqual(pool.load_config(pool.CONFIG_PATH)['hosts'], [])

    def setUp(self):
        self.config = pool.load_config(pool.CONFIG_PATH)
        self.config['hosts'] = [
            dict(env_label='Workstation', ssh='workstation', role='primary', enabled=True,
                 hostnames=['Workstation-PC']),
            dict(env_label='Laptop', ssh='laptop', role='personal', enabled=True,
                 hostnames=['Laptop-Computer']),
        ]
        self.host = dict(env_label='test', ssh='test', role='primary', enabled=True)

    def assess(self, host=None, **overrides):
        return pool.assess(reading(**overrides), host or self.host, self.config['roles'])

    def test_linux_fixtures_use_available_not_free(self):
        self.assertEqual(pool.parse_linux_memory(LINUX_MEMORY), dict(
            available_memory_gib=16, total_memory_gib=62, swap_used_fraction=0.25))
        self.assertEqual(pool.parse_linux_pressure(LINUX_PRESSURE), 2.5)
        self.assertEqual(pool.parse_linux_memory(LINUX_MEMORY.replace('8388608', '0'))[
            'swap_used_fraction'], 0)
        with self.assertRaises(ValueError):
            pool.parse_linux_pressure('full avg60=0.00')

    def test_mac_fixtures_respect_page_size_and_units(self):
        self.assertEqual(pool.parse_macos_memory(MAC_MEMORY), 9)
        self.assertEqual(pool.parse_macos_memory(MAC_MEMORY.replace('16384', '4096')), 2.25)
        self.assertEqual(pool.parse_macos_swap(MAC_SWAP), 0.25)
        self.assertEqual(pool.parse_macos_swap('total = 2.00G used = 512.00M'), 0.25)
        self.assertEqual(pool.parse_macos_swap('total = 0.00M used = 0.00M'), 0)
        self.assertTrue(pool.parse_macos_ac("Now drawing from 'AC Power'\n -InternalBattery-0"))
        self.assertFalse(pool.parse_macos_ac("Now drawing from 'Battery Power'"))
        self.assertEqual(pool.parse_macos_idle(' | "HIDIdleTime" = 900000000000'), 900)
        with self.assertRaises(ValueError):
            pool.parse_macos_ac('unavailable')

    def test_busy_thresholds_and_exact_boundaries(self):
        safe = self.assess(available_memory_gib=8, memory_pressure=5,
                           swap_used_fraction=0.8, load_per_core=1.0, free_disk_gib=15)
        self.assertFalse(safe['busy'])
        self.assertTrue(safe['eligible_for_new_work'])
        for change in (dict(available_memory_gib=7.99), dict(memory_pressure=5.01),
                       dict(swap_used_fraction=0.801), dict(load_per_core=1.01)):
            with self.subTest(change=change):
                result = self.assess(**change)
                self.assertTrue(result['busy'])
                self.assertFalse(result['eligible_for_new_work'])
                self.assertEqual(len(result['busy_reasons']), 1)
        for level in (1, 2, 4):
            result = self.assess(memory_pressure_kind='macos_level', memory_pressure=level)
            self.assertEqual(result['busy'], level >= 2)

    def test_mac_high_dynamic_swap_with_normal_pressure_is_not_busy(self):
        result = self.assess(system='Darwin', total_memory_gib=16, available_memory_gib=6.6,
                             memory_pressure_kind='macos_level', memory_pressure=1,
                             swap_used_fraction=0.88)
        self.assertFalse(result['busy'])
        self.assertTrue(result['eligible_for_new_work'])
        self.assertEqual(result['busy_reasons'], [])
        warned = self.assess(system='Darwin', total_memory_gib=16, available_memory_gib=6.6,
                             memory_pressure_kind='macos_level', memory_pressure=2,
                             swap_used_fraction=0.88)
        self.assertEqual(warned['busy_reasons'], ['macOS pressure >= 2'])

    def test_available_ram_threshold_scales_to_quarter_total_capped_at_eight(self):
        for total, threshold in ((8, 2), (16, 4), (32, 8), (62, 8)):
            with self.subTest(total=total):
                self.assertFalse(self.assess(total_memory_gib=total,
                                              available_memory_gib=threshold)['busy'])
                below = self.assess(total_memory_gib=total, available_memory_gib=threshold - 0.01)
                self.assertTrue(below['busy'])
                self.assertEqual(below['busy_reasons'], ['available RAM < {} GiB'.format(threshold)])

    def test_disk_disabled_unknown_and_unreachable_are_excluded(self):
        disk = self.assess(free_disk_gib=14.99)
        self.assertFalse(disk['busy'])
        self.assertFalse(disk['eligible_for_new_work'])
        self.host['enabled'] = False
        self.assertFalse(self.assess()['eligible_for_new_work'])
        unknown = pool.assess(reading(), None, self.config['roles'])
        self.assertFalse(unknown['eligible_for_new_work'])
        self.assertIn('host is not configured', unknown['eligibility_reasons'])
        unreachable = pool.assess(dict(reachable=False), self.host, self.config['roles'])
        self.assertFalse(unreachable['eligible_for_new_work'])
        self.assertEqual(unreachable['headroom'], 0)
        self.assertEqual(unreachable['task_cap'], 0)
        self.assertIn('host unreachable', unreachable['busy_reasons'][0])
        self.assertIn('no', pool.table([dict(unreachable, target='test')]))

    def test_personal_requires_known_ac_and_idle_even_when_local(self):
        self.host['role'] = 'personal'
        for ac, idle, eligible in ((True, 900, True), (True, 899, False),
                                   (False, 900, False), (None, 900, False),
                                   (True, None, False), (None, None, False)):
            with self.subTest(ac=ac, idle=idle):
                result = self.assess(on_ac_power=ac, user_idle_seconds=idle)
                self.assertEqual(result['eligible_for_new_work'], eligible)
                self.assertEqual(bool(result['personal_eligibility_reasons']), not eligible)
        self.assertFalse(self.assess(on_ac_power=True, user_idle_seconds=1000,
                                     free_disk_gib=10)['eligible_for_new_work'])
        self.assertFalse(self.assess(on_ac_power=True, user_idle_seconds=1000,
                                     load_per_core=2)['eligible_for_new_work'])

    def test_caps_are_scaled_and_config_driven(self):
        expected = {'dedicated': 10, 'primary': 15, 'personal': 1}
        for role, cap in expected.items():
            self.assertEqual(pool.task_cap(reading(), self.config['roles'][role]), cap)
        self.assertEqual(pool.task_cap(reading(cores=10, total_memory_gib=16),
                                       self.config['roles']['primary']), 4)
        self.assertEqual(pool.task_cap(reading(cores=64, total_memory_gib=128),
                                       self.config['roles']['primary']), 16)
        limits = dict(max_tasks=20, cores_per_task=4, ram_gib_per_task=8)
        self.assertEqual(pool.task_cap(reading(), limits), 7)
        self.assertEqual(pool.task_cap(reading(cores=1), limits), 0)
        self.assertEqual(self.assess(cores=1)['task_cap'], 0)
        self.assertFalse(self.assess(cores=1)['eligible_for_new_work'])

    def test_headroom_is_comparable_and_decreases_for_reserved_resources(self):
        initial = self.assess()
        self.assertEqual(initial['headroom'], 4)
        reserved = self.assess(available_memory_gib=18, load_per_core=0.25 + 2 / 32)
        self.assertEqual(reserved['headroom'], 3)
        self.assertEqual(self.assess(load_per_core=2)['headroom'], 0)

    def test_remote_source_is_self_contained_and_timeout_is_bounded(self):
        with patch.object(pool.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 0, json.dumps(reading()))) as run:
            self.assertTrue(pool.probe('test')['reachable'])
        args, kwargs = run.call_args
        self.assertEqual(args[0], ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                                   'test', 'python3 -'])
        self.assertEqual(kwargs['timeout'], 20)
        self.assertNotIn('CONFIG_PATH', kwargs['input'])
        compile(kwargs['input'], '<remote probe>', 'exec')
        with patch.object(pool.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ssh', 20)):
            self.assertFalse(pool.probe('test')['reachable'])
        with patch.object(pool.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 0, 'not json')):
            self.assertFalse(pool.probe('test')['reachable'])
        for invalid in ({}, reading(load_per_core=float('nan')), reading(cores=0)):
            with self.subTest(invalid=invalid), patch.object(
                    pool.subprocess, 'run', return_value=subprocess.CompletedProcess(
                        [], 0, json.dumps(invalid))):
                self.assertFalse(pool.probe('test')['reachable'])

    def test_mac_measurement_uses_fixture_commands_and_handles_missing_idle(self):
        responses = {'/usr/bin/vm_stat': MAC_MEMORY, 'hw.memsize': str(16 * pool.GIB),
                     'hw.ncpu': '10', 'kern.memorystatus_vm_pressure_level': '1',
                     'vm.swapusage': MAC_SWAP, '/usr/bin/pmset': "Now drawing from 'AC Power'",
                     '/usr/sbin/ioreg': 'missing idle'}

        def command(*args):
            return responses[args[-1] if args[0] == '/usr/sbin/sysctl' else args[0]]

        with patch.object(pool.platform, 'system', return_value='Darwin'), \
                patch.object(pool, 'command', side_effect=command), \
                patch.object(pool.os, 'getloadavg', return_value=(5, 4, 3)), \
                patch.object(pool.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 20 * pool.GIB})):
            result = pool.measure_host()
        self.assertEqual(result['cores'], 10)
        self.assertEqual(result['load_per_core'], 0.5)
        self.assertEqual(result['available_memory_gib'], 9)
        self.assertEqual(result['total_memory_gib'], 16)
        self.assertEqual(result['free_disk_gib'], 20)
        self.assertTrue(result['on_ac_power'])
        self.assertIsNone(result['user_idle_seconds'])
        self.assertEqual(len(result['personal_reading_errors']), 1)

    def test_main_maps_labels_deduplicates_and_identifies_local(self):
        with patch.object(pool, 'load_config', return_value=self.config), \
                patch.object(pool.socket, 'gethostname', return_value='workstation.local'), \
                patch.object(pool, 'probe', return_value=reading()) as probe, \
                redirect_stdout(io.StringIO()) as out:
            pool.main(['--env-label', 'Laptop', '--ssh', 'laptop', '--ssh', 'workstation'])
        result = json.loads(out.getvalue())['hosts']
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(result[0]['role'], 'primary')
        self.assertEqual(result[0]['env_label'], 'Workstation')
        self.assertTrue(result[0]['local'])
        self.assertEqual(result[1]['target'], 'laptop')
        self.assertEqual(result[1]['role'], 'personal')
        self.assertFalse(result[1]['eligible_for_new_work'])

    def test_local_host_aliases_match_both_real_os_hostnames(self):
        for hostname, role, ssh in (('Workstation-PC', 'primary', 'workstation'),
                                    ('Laptop-Computer.local', 'personal', 'laptop')):
            with self.subTest(hostname=hostname), \
                    patch.object(pool, 'load_config', return_value=self.config), \
                    patch.object(pool.socket, 'gethostname', return_value=hostname), \
                    patch.object(pool, 'probe', return_value=reading()) as probe, \
                    redirect_stdout(io.StringIO()) as out:
                pool.main(['--ssh', ssh])
                result = json.loads(out.getvalue())['hosts']
                self.assertEqual(probe.call_count, 1)
                self.assertEqual(result[0]['role'], role)
                self.assertEqual(len(result), 1)

    def test_config_rejects_unsafe_targets_and_invalid_roles_caps(self):
        for target in ('-oProxyCommand=bad', '-Fconfig@host', '-user@host',
                       'test;bad', 'test host', '$(bad)'):
            self.assertFalse(pool.valid_ssh_target(target))
        for target in ('test', 'user@host.local', '100.1.2.3'):
            self.assertTrue(pool.valid_ssh_target(target))
        for mutate in (lambda c: c['hosts'][0].update(role='invalid'),
                       lambda c: c['hosts'][0].update(enabled='false'),
                       lambda c: c['hosts'].append(c['hosts'][0]),
                       lambda c: c['roles']['primary'].update(max_tasks=0)):
            config = copy.deepcopy(self.config)
            mutate(config)
            with patch.object(pool.Path, 'read_text', return_value=json.dumps(config)):
                with self.assertRaises(ValueError):
                    pool.load_config('unused')

    def test_local_matching_preserves_domains_and_requires_explicit_aliases(self):
        host = dict(ssh='user@worker.remote.example')
        self.assertTrue(pool.matches_local(host, 'WORKER.REMOTE.EXAMPLE'))
        self.assertFalse(pool.matches_local(host, 'worker.local.example'))
        self.assertFalse(pool.matches_local(host, 'worker'))
        host['hostnames'] = ['worker-alias']
        self.assertTrue(pool.matches_local(host, 'worker-alias.local'))
        self.assertFalse(pool.matches_local(host, 'worker-alias.other.example'))

    def test_same_short_name_remote_is_probed_and_not_labelled_local(self):
        self.config['hosts'] = [dict(env_label='Remote', ssh='worker.remote.example',
                                    role='dedicated', enabled=True)]
        with patch.object(pool, 'load_config', return_value=self.config), \
                patch.object(pool.socket, 'gethostname', return_value='worker.local.example'), \
                patch.object(pool, 'probe', return_value=reading()) as probe, \
                redirect_stdout(io.StringIO()) as out:
            pool.main(['--env-label', 'Remote'])
        self.assertCountEqual([call.args[0] for call in probe.call_args_list],
                              [None, 'worker.remote.example'])
        local, remote = json.loads(out.getvalue())['hosts']
        self.assertIsNone(local['env_label'])
        self.assertIsNone(local['role'])
        self.assertTrue(local['local'])
        self.assertEqual(remote['env_label'], 'Remote')
        self.assertEqual(remote['role'], 'dedicated')
        self.assertFalse(remote['local'])

    def test_documented_host_example_is_a_valid_entry(self):
        reference = SCRIPT.parents[1] / 'references/t3-code.md'
        examples = re.findall(r'```json\n(.*?)\n```', reference.read_text(), re.S)
        self.assertTrue(examples, 'missing JSON host entry example')
        config = copy.deepcopy(self.config)
        config['hosts'] = [json.loads(examples[0])]
        with patch.object(pool.Path, 'read_text', return_value=json.dumps(config)):
            self.assertEqual(pool.load_config('unused')['hosts'], config['hosts'])


if __name__ == '__main__':
    unittest.main()
