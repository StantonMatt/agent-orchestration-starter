#!/usr/bin/env python3
"""Read-only Linux/macOS compute-pool telemetry; JSON by default, --table for people.

Config lives beside the repo's other config (resolved through installed symlinks).
Unknown hosts can be measured with --ssh but cannot receive work until configured.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor as ThreadPool
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess

GIB = 1024 ** 3


def parse_linux_memory(text):
    values = {key: int(value) * 1024 for key, value in
              re.findall(r"^(\w+):\s+(\d+) kB", text, re.M)}
    total_swap = values['SwapTotal']
    return {'available_memory_gib': values['MemAvailable'] / GIB,
            'total_memory_gib': values['MemTotal'] / GIB,
            'swap_used_fraction': ((total_swap - values['SwapFree']) / total_swap
                                   if total_swap else 0.0)}


def parse_linux_pressure(text):
    match = re.search(r'^some\s+.*?\bavg60=([\d.]+)', text, re.M)
    if not match:
        raise ValueError('missing memory PSI some avg60')
    return float(match[1])


def parse_macos_memory(text):
    page_size = int(re.search(r'page size of (\d+) bytes', text)[1])
    pages = dict(re.findall(r'^Pages (free|inactive|speculative):\s+(\d+)\.', text, re.M))
    return sum(int(pages[key]) for key in ('free', 'inactive', 'speculative')) * page_size / GIB


def parse_macos_swap(text):
    sizes = {name: float(value) * (1024 ** 'BKMGTP'.index(unit.upper()))
             for name, value, unit in re.findall(
                 r'\b(total|used)\s*=\s*([\d.]+)([BKMGTP])', text, re.I)}
    return sizes['used'] / sizes['total'] if sizes['total'] else 0.0


def parse_macos_ac(text):
    match = re.search(r"Now drawing from '(AC Power|Battery Power)'", text)
    if not match:
        raise ValueError('missing power source')
    return match[1] == 'AC Power'


def parse_macos_idle(text):
    return int(re.search(r'"HIDIdleTime"\s*=\s*(\d+)', text)[1]) / 1_000_000_000


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=3).stdout


def measure_host():
    system = platform.system()
    result = {'hostname': socket.gethostname(), 'system': system,
              'on_ac_power': None, 'user_idle_seconds': None, 'personal_reading_errors': []}
    if system == 'Linux':
        result.update(parse_linux_memory(Path('/proc/meminfo').read_text()))
        result['memory_pressure'] = parse_linux_pressure(Path('/proc/pressure/memory').read_text())
        result['memory_pressure_kind'] = 'psi_some_avg60'
        result['cores'] = os.cpu_count()
    elif system == 'Darwin':
        result['available_memory_gib'] = parse_macos_memory(command('/usr/bin/vm_stat'))
        result['total_memory_gib'] = int(command('/usr/sbin/sysctl', '-n', 'hw.memsize')) / GIB
        result['cores'] = int(command('/usr/sbin/sysctl', '-n', 'hw.ncpu'))
        result['memory_pressure'] = int(command('/usr/sbin/sysctl', '-n',
                                               'kern.memorystatus_vm_pressure_level'))
        result['memory_pressure_kind'] = 'macos_level'
        result['swap_used_fraction'] = parse_macos_swap(command('/usr/sbin/sysctl', 'vm.swapusage'))
        for key, parser, args in (
                ('on_ac_power', parse_macos_ac, ('/usr/bin/pmset', '-g', 'batt')),
                ('user_idle_seconds', parse_macos_idle, ('/usr/sbin/ioreg', '-c', 'IOHIDSystem'))):
            try:
                result[key] = parser(command(*args))
            except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
                result['personal_reading_errors'].append('{}: {}'.format(key, exc))
    else:
        raise ValueError('unsupported OS: ' + system)
    result['load_per_core'] = os.getloadavg()[0] / result['cores']
    result['free_disk_gib'] = shutil.disk_usage(Path.home()).free / GIB
    return result

# END PROBE

MAX_AVAILABLE_THRESHOLD_GIB = 8
MIN_AVAILABLE_RAM_FRACTION = 0.25
MAX_PSI_AVG60 = 5
MACOS_WARN_PRESSURE = 2
MAX_SWAP_FRACTION = 0.8
MAX_LOAD_PER_CORE = 1.0
MIN_DISK_GIB = 15
MIN_PERSONAL_IDLE_SECONDS = 15 * 60
SSH_TIMEOUT_SECONDS = 20
HEADROOM_RAM_GIB_PER_TASK = 6
HEADROOM_CORES_PER_TASK = 2
CONFIG_PATH = Path(__file__).resolve().parents[1] / 'config/compute-pool.json'


def load_config(path):
    config = json.loads(Path(path).read_text())
    if set(config['roles']) != {'dedicated', 'primary', 'personal'}:
        raise ValueError('roles must be dedicated, primary and personal')
    for limits in config['roles'].values():
        if set(limits) != {'max_tasks', 'cores_per_task', 'ram_gib_per_task'}:
            raise ValueError('invalid role cap fields')
        if not all(type(value) in (int, float) and math.isfinite(value) and value > 0
                   for value in limits.values()) or type(limits['max_tasks']) is not int:
            raise ValueError('role caps must be positive; max_tasks must be an integer')
    labels, targets = set(), set()
    for host in config['hosts']:
        if (host['role'] not in config['roles'] or type(host['enabled']) is not bool
                or not isinstance(host['env_label'], str) or not host['env_label']
                or not isinstance(host['ssh'], str) or not valid_ssh_target(host['ssh'])
                or not isinstance(host.get('hostnames', []), list)
                or not all(isinstance(name, str) and name for name in host.get('hostnames', []))):
            raise ValueError('invalid host entry')
        if host['env_label'] in labels or host['ssh'] in targets:
            raise ValueError('duplicate environment label or SSH target')
        labels.add(host['env_label'])
        targets.add(host['ssh'])
    return config


def valid_ssh_target(target):
    # SSH aliases or user@host only; never allow options, shell syntax or whitespace.
    return not target.startswith('-') and bool(
        re.fullmatch(r'(?:[\w.-]+@)?[\w][\w.-]*', target, re.ASCII))


def matches_local(host, hostname):
    names = [host['ssh'].split('@')[-1]] + host.get('hostnames', [])

    def normalize(name):
        name = name.casefold()
        return name[:-6] if name.endswith('.local') else name

    return any(normalize(name) == normalize(hostname) for name in names)


def task_cap(readings, limits):
    return max(0, min(limits['max_tasks'], int(readings['cores'] / limits['cores_per_task']),
                      int(readings['total_memory_gib'] / limits['ram_gib_per_task'])))


def assess(readings, host, roles):
    result = dict(readings, role=host['role'] if host else None,
                  enabled=host['enabled'] if host else False)
    busy_reasons = []
    reasons = []
    if not readings.get('reachable'):
        busy_reasons.append('host unreachable or measurement failed')
    else:
        minimum_available = min(MAX_AVAILABLE_THRESHOLD_GIB,
                                readings['total_memory_gib'] * MIN_AVAILABLE_RAM_FRACTION)
        for condition, reason in (
                (readings['available_memory_gib'] < minimum_available,
                 'available RAM < {:g} GiB'.format(minimum_available)),
                (readings['memory_pressure_kind'] == 'psi_some_avg60'
                 and readings['memory_pressure'] > MAX_PSI_AVG60, 'memory PSI avg60 > 5'),
                (readings['memory_pressure_kind'] == 'macos_level'
                 and readings['memory_pressure'] >= MACOS_WARN_PRESSURE, 'macOS pressure >= 2'),
                (readings['memory_pressure_kind'] == 'psi_some_avg60'
                 and readings['swap_used_fraction'] > MAX_SWAP_FRACTION, 'swap used > 80%'),
                (readings['load_per_core'] > MAX_LOAD_PER_CORE, 'load/core > 1.0')):
            if condition:
                busy_reasons.append(reason)
        if readings['free_disk_gib'] < MIN_DISK_GIB:
            reasons.append('free home-volume disk < 15 GiB')
    if not host:
        reasons.append('host is not configured')
    elif not host['enabled']:
        reasons.append('host disabled in config')
    personal_reasons = []
    if result['role'] == 'personal':
        if readings.get('on_ac_power') is not True:
            personal_reasons.append('AC power unavailable or not connected')
        idle = readings.get('user_idle_seconds')
        if idle is None or idle < MIN_PERSONAL_IDLE_SECONDS:
            personal_reasons.append('user idle unavailable or < 900 seconds')
    cap = task_cap(readings, roles[host['role']]) if host and readings.get('reachable') else 0
    if cap == 0:
        reasons.append('task cap is zero')
    reasons += busy_reasons + personal_reasons
    # Worker-equivalent spare RAM/CPU; eligibility separately gates pressure/swap/disk.
    headroom = (min(readings['available_memory_gib'] / HEADROOM_RAM_GIB_PER_TASK,
                    max(0, readings['cores'] * (1 - readings['load_per_core'])) /
                    HEADROOM_CORES_PER_TASK) if readings.get('reachable') else 0.0)
    result.update(busy=bool(busy_reasons), busy_reasons=busy_reasons,
                  eligible_for_new_work=not reasons, eligibility_reasons=reasons,
                  personal_eligibility_reasons=personal_reasons, task_cap=cap,
                  headroom=round(headroom, 3))
    return result


def validate_readings(readings):
    for key in ('cores', 'total_memory_gib', 'available_memory_gib', 'memory_pressure',
                'swap_used_fraction', 'load_per_core', 'free_disk_gib'):
        value = readings[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid reading: ' + key)
    if (readings['cores'] <= 0 or readings['total_memory_gib'] <= 0
            or readings['swap_used_fraction'] > 1
            or readings['memory_pressure_kind'] not in ('psi_some_avg60', 'macos_level')):
        raise ValueError('invalid measurement range or pressure kind')
    return dict(readings, reachable=True)


def probe(target=None):
    try:
        if target is None:
            return validate_readings(measure_host())
        source = Path(__file__).read_text().split('\n# END PROBE\n', 1)[0]
        completed = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', target, 'python3 -'],
            input=source + '\nprint(json.dumps(measure_host()))\n', text=True,
            capture_output=True, check=True, timeout=SSH_TIMEOUT_SECONDS)
        return validate_readings(json.loads(completed.stdout))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return {'reachable': False, 'error': str(exc)}


def table(hosts):
    rows = [['HOST', 'ROLE', 'ON', 'RAM avail/total GiB', 'CORES', 'PRESSURE', 'SWAP',
             'LOAD/C', 'DISK GiB', 'AC', 'IDLE s', 'BUSY', 'ELIGIBLE', 'CAP', 'HEADROOM']]
    for host in hosts:
        if not host['reachable']:
            rows.append([host['target'], host['role'] or '?', str(host['enabled']),
                         *(['-'] * 8), 'yes', 'no', '0', '0'])
            continue
        rows.append([host['target'], host['role'] or '?', str(host['enabled']),
                     '{:.1f}/{:.1f}'.format(host['available_memory_gib'], host['total_memory_gib']),
                     str(host['cores']), '{}:{}'.format(host['memory_pressure_kind'], host['memory_pressure']),
                     '{:.0%}'.format(host['swap_used_fraction']), '{:.2f}'.format(host['load_per_core']),
                     '{:.1f}'.format(host['free_disk_gib']), str(host['on_ac_power']),
                     '-' if host['user_idle_seconds'] is None else '{:.0f}'.format(host['user_idle_seconds']),
                     str(host['busy']), str(host['eligible_for_new_work']), str(host['task_cap']),
                     str(host['headroom'])])
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ['  '.join(cell.ljust(width) for cell, width in zip(row, widths)) for row in rows]
    for host in hosts:
        if host['eligibility_reasons']:
            lines.append('{}: {}'.format(host['target'], '; '.join(host['eligibility_reasons'])))
        if host.get('error'):
            lines.append('{}: {}'.format(host['target'], host['error']))
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG_PATH)
    parser.add_argument('--env-label', action='append', default=[])
    parser.add_argument('--ssh', action='append', default=[])
    parser.add_argument('--table', action='store_true')
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        labels = {host['env_label']: host for host in config['hosts']}
        targets = {host['ssh']: host for host in config['hosts']}
        remote = list(args.ssh)
        for label in args.env_label:
            if label not in labels:
                parser.error('unmapped environment label {!r}; add it to {}'.format(label, args.config))
            remote.append(labels[label]['ssh'])
        if not all(valid_ssh_target(target) for target in remote):
            parser.error('invalid SSH target')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error('invalid compute-pool config: {}'.format(exc))
    local_host = next((host for host in config['hosts']
                       if matches_local(host, socket.gethostname())), None)
    requests = [(None, local_host)]
    for target in dict.fromkeys(remote):
        if not (local_host and target == local_host['ssh']) and not matches_local(
                {'ssh': target}, socket.gethostname()):
            requests.append((target, targets.get(target)))
    with ThreadPool(max_workers=min(32, len(requests))) as probes:
        readings = list(probes.map(probe, (target for target, _ in requests)))
    hosts = []
    for (target, host), reading in zip(requests, readings):
        result = assess(reading, host, config['roles'])
        result.update(target=target or socket.gethostname(), local=target is None,
                      env_label=host['env_label'] if host else None)
        hosts.append(result)
    print(table(hosts) if args.table else json.dumps({'hosts': hosts}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
