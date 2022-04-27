from hashlib import sha1
from typing import Dict, Optional, cast
from argparse import ArgumentParser as CoreArgumentParser, Namespace
from os import getcwd, environ, chdir, path
from shutil import rmtree

import pytest

from _pytest.capture import CaptureFixture
from _pytest.tmpdir import TempPathFactory
from pytest_mock import MockerFixture

from grizzly_cli.__main__ import _create_parser, _parse_arguments, main

from .helpers import onerror

CWD = getcwd()


def test__create_parser() -> None:
    parser = _create_parser()

    assert parser.prog == 'grizzly-cli'
    assert parser.description is not None
    assert 'pip install grizzly-loadtester-cli' in parser.description
    assert 'eval "$(grizzly-cli --bash-completion)"' in parser.description
    assert parser._subparsers is not None
    assert len(parser._subparsers._group_actions) == 1
    assert sorted([option_string for action in parser._actions for option_string in action.option_strings]) == sorted([
        '-h', '--help',
        '--version',
        '--md-help',
        '--bash-completion',
    ])
    assert sorted([action.dest for action in parser._actions if len(action.option_strings) == 0]) == ['command']
    subparser = parser._subparsers._group_actions[0]
    assert subparser is not None
    assert subparser.choices is not None
    assert len(cast(Dict[str, Optional[CoreArgumentParser]], subparser.choices).keys()) == 3

    init_parser = cast(Dict[str, Optional[CoreArgumentParser]], subparser.choices).get('init', None)
    assert init_parser is not None
    assert init_parser._subparsers is None
    assert getattr(init_parser, 'prog', None) == 'grizzly-cli init'
    assert sorted([option_string for action in init_parser._actions for option_string in action.option_strings]) == sorted([
        '-h', '--help',
        '--with-mq',
        '--grizzly-version',
    ])

    local_parser = cast(Dict[str, Optional[CoreArgumentParser]], subparser.choices).get('local', None)
    assert local_parser is not None
    assert local_parser._subparsers is not None
    assert getattr(local_parser, 'prog', None) == 'grizzly-cli local'
    assert sorted([option_string for action in local_parser._actions for option_string in action.option_strings]) == sorted([
        '-h', '--help',
    ])
    assert len(local_parser._subparsers._group_actions) == 1
    local_subparser = local_parser._subparsers._group_actions[0]
    assert local_subparser is not None
    assert local_subparser.choices is not None
    assert list(cast(Dict[str, Optional[CoreArgumentParser]], local_subparser.choices).keys()) == ['run']

    dist_parser = cast(Dict[str, Optional[CoreArgumentParser]], subparser.choices).get('dist', None)
    assert dist_parser is not None
    assert dist_parser._subparsers is not None
    assert getattr(dist_parser, 'prog', None) == 'grizzly-cli dist'
    assert sorted([option_string for action in dist_parser._actions for option_string in action.option_strings]) == sorted([
        '-h', '--help',
        '--force-build', '--build', '--validate-config',
        '--workers',
        '--id',
        '--limit-nofile',
        '--container-system',
        '--health-timeout',
        '--health-retries',
        '--health-interval',
        '--registry',
        '--tty',
    ])
    assert sorted([action.dest for action in dist_parser._actions if len(action.option_strings) == 0]) == ['subcommand']
    assert len(dist_parser._subparsers._group_actions) == 1
    dist_subparser = dist_parser._subparsers._group_actions[0]
    assert dist_subparser is not None
    assert dist_subparser.choices is not None
    assert list(cast(Dict[str, Optional[CoreArgumentParser]], dist_subparser.choices).keys()) == ['build', 'run']

    dist_build_parser = cast(Dict[str, Optional[CoreArgumentParser]], dist_subparser.choices).get('build', None)
    assert dist_build_parser is not None
    assert dist_build_parser._subparsers is None
    assert getattr(dist_build_parser, 'prog', None) == 'grizzly-cli dist build'
    assert sorted([option_string for action in dist_build_parser._actions for option_string in action.option_strings]) == sorted([
        '-h', '--help',
        '--no-cache',
        '--registry',
    ])

    # grizzly-cli ... run
    for tested_parser, parent in [(local_parser, 'local',), (dist_parser, 'dist',)]:
        assert tested_parser._subparsers is not None
        assert len(tested_parser._subparsers._group_actions) == 1
        subparser = tested_parser._subparsers._group_actions[0]
        run_parser = cast(Dict[str, Optional[CoreArgumentParser]], subparser.choices).get('run', None)
        assert run_parser is not None
        assert getattr(run_parser, 'prog', None) == f'grizzly-cli {parent} run'
        assert sorted([option_string for action in run_parser._actions for option_string in action.option_strings]) == sorted([
            '-h', '--help',
            '--verbose',
            '-T', '--testdata-variable',
            '-y', '--yes',
            '-e', '--environment-file',
        ])
        assert sorted([action.dest for action in run_parser._actions if len(action.option_strings) == 0]) == ['file']


def test__parse_argument(capsys: CaptureFixture, mocker: MockerFixture, tmp_path_factory: TempPathFactory) -> None:
    test_context = tmp_path_factory.mktemp('test_context')
    (test_context / 'test.feature').write_text('Feature:')
    test_context_root = str(test_context)

    import sys

    try:
        mocker.patch('grizzly_cli.EXECUTION_CONTEXT', test_context_root)
        chdir(test_context_root)
        sys.argv = ['grizzly-cli']

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 2
        capture = capsys.readouterr()
        assert capture.out == ''
        assert 'usage: grizzly-cli' in capture.err
        assert 'grizzly-cli: error: no command specified' in capture.err

        sys.argv = ['grizzly-cli', '--version']

        mocker.patch('grizzly_cli.__main__.__version__', '0.0.0')

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 0
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == 'grizzly-cli (development)\n'

        sys.argv = ['grizzly-cli', '--version', 'foo']

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 2
        capture = capsys.readouterr()
        err = capture.err.split('\n')
        assert len(err) == 3
        assert err[0].startswith('usage: grizzly-cli')
        assert err[1] == (
            "grizzly-cli: error: argument --version: invalid choice: 'foo' (choose from 'all')"
        )
        assert err[2] == ''
        assert capture.out == ''

        requirements_file = test_context / 'requirements.txt'
        requirements_file.write_text('grizzly-loadtester==1.5.3\n')

        sys.argv = ['grizzly-cli', '--version', 'all']

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 0
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            'grizzly-cli (development)\n'
            '└── grizzly 1.5.3\n'
            '    └── locust 2.2.1\n'
        )

        requirements_file.write_text('grizzly-loadtester[mq]==1.5.3\n')

        sys.argv = ['grizzly-cli', '--version', 'all']

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 0
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            'grizzly-cli (development)\n'
            '└── grizzly 1.5.3 ── extras: mq\n'
            '    └── locust 2.2.1\n'
        )

        requirements_file.unlink()
        requirements_file.write_text('grizzly-loadtester[mq,dev]==1.5.3\n')

        sys.argv = ['grizzly-cli', '--version', 'all']

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 0
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            'grizzly-cli (development)\n'
            '└── grizzly 1.5.3 ── extras: mq, dev\n'
            '    └── locust 2.2.1\n'
        )

        def mocked_mkdtemp(prefix: Optional[str] = '') -> str:
            tmp_dir = path.join(test_context, f'{prefix}test')

            return tmp_dir

        mocker.patch('grizzly_cli.utils.mkdtemp', mocked_mkdtemp)
        mocker.patch('grizzly_cli.utils.subprocess.check_call', return_value=0)
        mocker.patch('grizzly_cli.utils.subprocess.check_output', return_value='main\n')

        repo = 'git+https://git@github.com/biometria-se/grizzly.git@main#egg=grizzly-loadtester'
        repo_suffix = sha1(repo.encode('utf-8')).hexdigest()
        repo_dir = test_context / 'grizzly-cli-test' / f'grizzly-loadtester_{repo_suffix}'
        repo_dir.mkdir(parents=True)
        (repo_dir / 'pyproject.toml').touch()
        (repo_dir / 'setup.cfg').write_text('name = grizzly-loadtester\nversion = 0.0.0\n')
        (repo_dir / 'requirements.txt').write_text('locust==2.8.4  \\ \n')

        requirements_file.unlink()
        requirements_file.write_text(f'{repo}\n')

        sys.argv = ['grizzly-cli', '--version', 'all']

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 0

        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            'grizzly-cli (development)\n'
            '└── grizzly (development)\n'
            '    └── locust 2.8.4\n'
        )

        repo = 'git+https://git@github.com/biometria-se/grizzly.git@main#egg=grizzly-loadtester[mq,dev]'
        repo_suffix = sha1(repo.encode('utf-8')).hexdigest()
        repo_dir = test_context / 'grizzly-cli-test' / f'grizzly-loadtester__mq_dev___{repo_suffix}'
        repo_dir.mkdir(parents=True)
        (repo_dir / 'pyproject.toml').touch()
        (repo_dir / 'setup.cfg').write_text('name = grizzly-loadtester\nversion = 0.0.0\n')
        (repo_dir / 'requirements.txt').write_text('locust==2.8.4  \\ \n')

        requirements_file.unlink()
        requirements_file.write_text(f'{repo}\n')

        sys.argv = ['grizzly-cli', '--version', 'all']

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 0

        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            'grizzly-cli (development)\n'
            '└── grizzly (development) ── extras: mq, dev\n'
            '    └── locust 2.8.4\n'
        )

        requirements_file.unlink()
        requirements_file.write_text('grizzly-loadtester==1.5.3\n')

        sys.argv = ['grizzly-cli', '--version', 'all']
        mocker.patch('grizzly_cli.__main__.__version__', '2.5.0')

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 0
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            'grizzly-cli 2.5.0\n'
            '└── grizzly 1.5.3\n'
            '    └── locust 2.2.1\n'
        )

        sys.argv = ['grizzly-cli', '--version', 'all']
        mocker.patch('grizzly_cli.__main__.__version__', '2.5.0')

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 0
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            'grizzly-cli 2.5.0\n'
            '└── grizzly 1.5.3\n'
            '    └── locust 2.2.1\n'
        )

        sys.argv = ['grizzly-cli', 'local']

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 2
        capture = capsys.readouterr()
        assert capture.out == ''
        assert 'grizzly-cli: error: no subcommand for local specified\n' == capture.err

        sys.argv = ['grizzly-cli', 'dist', 'run', 'test.feature']

        mocker.patch('grizzly_cli.__main__.get_distributed_system', side_effect=[None])

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 2
        capture = capsys.readouterr()
        assert capture.out == ''
        assert capture.err == 'grizzly-cli: error: cannot run distributed\n'

        mocker.patch('grizzly_cli.EXECUTION_CONTEXT', getcwd())
        mocker.patch('grizzly_cli.__main__.get_distributed_system', side_effect=['docker'])
        mocker.patch('grizzly_cli.distributed.do_build', side_effect=[0, 4, 0])

        sys.argv = ['grizzly-cli', 'dist', '--limit-nofile', '100', '--registry', 'ghcr.io/biometria-se', 'run', 'test.feature']
        (test_context / 'requirements.txt').write_text('grizzly-loadtester')
        mocker.patch('grizzly_cli.__main__.get_distributed_system', side_effect=['docker'])
        ask_yes_no = mocker.patch('grizzly_cli.__main__.ask_yes_no', autospec=True)

        arguments = _parse_arguments()
        capture = capsys.readouterr()
        assert arguments.limit_nofile == 100
        assert not arguments.yes
        assert arguments.registry == 'ghcr.io/biometria-se/'
        assert capture.out == '!! this will cause warning messages from locust later on\n'
        assert capture.err == ''
        assert ask_yes_no.call_count == 1
        args, _ = ask_yes_no.call_args_list[-1]
        assert args[0] == 'are you sure you know what you are doing?'

        sys.argv = ['grizzly-cli', 'local', 'run', 'test.feature']
        mocker.patch('grizzly_cli.__main__.which', side_effect=[None])

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 2

        capture = capsys.readouterr()
        assert capture.out == ''
        assert capture.err == 'grizzly-cli: error: "behave" not found in PATH, needed when running local mode\n'

        sys.argv = ['grizzly-cli', 'local', 'run', '-T', 'variable', 'test.feature']
        mocker.patch('grizzly_cli.__main__.which', side_effect=['behave'])

        with pytest.raises(SystemExit) as se:
            _parse_arguments()
        assert se.type == SystemExit
        assert se.value.code == 2

        capture = capsys.readouterr()
        assert capture.out == ''
        assert capture.err == 'grizzly-cli: error: -T/--testdata-variable needs to be in the format NAME=VALUE\n'

        sys.argv = ['grizzly-cli', 'local', 'run', '-T', 'key=value', 'test.feature']
        mocker.patch('grizzly_cli.__main__.which', side_effect=['behave'])

        assert environ.get('TESTDATA_VARIABLE_key', None) is None

        arguments = _parse_arguments()
        assert arguments.command == 'local'
        assert arguments.subcommand == 'run'
        assert arguments.file == 'test.feature'

        assert environ.get('TESTDATA_VARIABLE_key', None) == 'value'

        mocker.patch('grizzly_cli.__main__.get_distributed_system', side_effect=['docker'] * 3)

        sys.argv = ['grizzly-cli', 'dist', 'build']
        arguments = _parse_arguments()

        assert not arguments.no_cache
        assert not arguments.force_build
        assert arguments.build
        assert arguments.registry is None

        sys.argv = ['grizzly-cli', 'dist', 'build', '--no-cache', '--registry', 'gchr.io/biometria-se']
        arguments = _parse_arguments()

        assert arguments.no_cache
        assert arguments.force_build
        assert not arguments.build
        assert arguments.registry == 'gchr.io/biometria-se/'

    finally:
        chdir(CWD)
        rmtree(test_context_root, onerror=onerror)


def test_main(mocker: MockerFixture, capsys: CaptureFixture) -> None:
    local_mock = mocker.patch('grizzly_cli.__main__.local', side_effect=[0])
    dist_mock = mocker.patch('grizzly_cli.__main__.distributed', side_effect=[1337])
    init_mock = mocker.patch('grizzly_cli.__main__.init', side_effect=[7331])
    mocker.patch('grizzly_cli.__main__._parse_arguments', side_effect=[
        Namespace(command='local'),
        Namespace(command='dist'),
        Namespace(command='init'),
        Namespace(command='foobar'),
        KeyboardInterrupt,
        ValueError('hello there'),
    ],)

    assert main() == 0
    assert local_mock.call_count == 1
    assert dist_mock.call_count == 0
    assert init_mock.call_count == 0

    assert main() == 1337
    assert local_mock.call_count == 1
    assert dist_mock.call_count == 1
    assert init_mock.call_count == 0

    assert main() == 7331
    assert local_mock.call_count == 1
    assert dist_mock.call_count == 1
    assert init_mock.call_count == 1

    assert main() == 1

    capture = capsys.readouterr()
    assert capture.err == ''
    assert capture.out == '\nunknown command foobar\n\n!! aborted grizzly-cli\n'

    assert main() == 1

    capture = capsys.readouterr()
    assert capture.err == ''
    assert capture.out == '\n\n!! aborted grizzly-cli\n'

    assert main() == 1

    capture = capsys.readouterr()
    assert capture.err == ''
    assert capture.out == '\nhello there\n\n!! aborted grizzly-cli\n'
