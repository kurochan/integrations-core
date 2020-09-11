# (C) Datadog, Inc. 2020-present
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
from typing import Any, List

import mock
import pytest
from packaging import version

from datadog_checks.base.stubs.aggregator import AggregatorStub
from datadog_checks.marklogic import MarklogicCheck

from .common import (
    COMMON_TAGS,
    INSTANCE,
    INSTANCE_FILTERS,
    INSTANCE_SIMPLE_USER,
    MARKLOGIC_VERSION,
    SERVICE_CHECKS_HEALTH_TAG,
)
from .metrics import (
    FOREST_STATUS_TREE_CACHE_METRICS,
    GLOBAL_METRICS,
    RESOURCE_STORAGE_FOREST_METRICS,
    STORAGE_FOREST_METRICS,
    STORAGE_HOST_METRICS,
)


def _assert_metrics(aggregator, tags):
    # type: (AggregatorStub, List[str]) -> None
    for metric in GLOBAL_METRICS:
        aggregator.assert_metric(metric, tags=tags)

    for metric in FOREST_STATUS_TREE_CACHE_METRICS:
        aggregator.assert_metric(metric, tags=tags)

    storage_tag_prefixes = ['storage_path', 'host_name', 'host_id']
    for metric in STORAGE_HOST_METRICS:
        for tag in tags:
            aggregator.assert_metric_has_tag(metric, tag)
        for prefix in storage_tag_prefixes:
            aggregator.assert_metric_has_tag_prefix(metric, prefix)
    for metric in STORAGE_FOREST_METRICS:
        for tag in tags:
            aggregator.assert_metric_has_tag(metric, tag)
        for prefix in storage_tag_prefixes + ['forest_id', 'forest_name']:
            aggregator.assert_metric_has_tag_prefix(metric, prefix)


def _assert_service_checks(aggregator, tags, count=1, include_health_checks=True):
    # type: (AggregatorStub, List[str], int, bool) -> None
    aggregator.assert_service_check('marklogic.can_connect', MarklogicCheck.OK, count=count)

    if include_health_checks:
        for database_tag in SERVICE_CHECKS_HEALTH_TAG['database']:
            aggregator.assert_service_check(
                'marklogic.database.health', MarklogicCheck.OK, tags=tags + [database_tag], count=count
            )

        for forest_tag in SERVICE_CHECKS_HEALTH_TAG['forest']:
            aggregator.assert_service_check(
                'marklogic.forest.health', MarklogicCheck.OK, tags=tags + [forest_tag], count=count
            )


@pytest.mark.integration
@pytest.mark.usefixtures("dd_environment")
def test_check(aggregator):
    # type: (AggregatorStub) -> None
    check = MarklogicCheck('marklogic', {}, [INSTANCE])

    check.check(INSTANCE)

    _assert_metrics(aggregator, COMMON_TAGS)

    aggregator.assert_all_metrics_covered()

    # Service checks
    _assert_service_checks(aggregator, COMMON_TAGS)

    aggregator.assert_no_duplicate_all()

    # aggregator.assert_metrics_using_metadata(get_metadata_metrics())


@pytest.mark.integration
@pytest.mark.usefixtures("dd_environment")
def test_check_simple_user(aggregator):
    # type: (AggregatorStub) -> None
    check = MarklogicCheck('marklogic', {}, [INSTANCE_SIMPLE_USER])

    check.check(INSTANCE_SIMPLE_USER)

    _assert_metrics(aggregator, COMMON_TAGS)

    aggregator.assert_all_metrics_covered()

    # Service checks
    _assert_service_checks(aggregator, COMMON_TAGS, include_health_checks=False)

    len(aggregator._service_checks) == 1  # can_connect service check only

    aggregator.assert_no_duplicate_all()


@pytest.mark.integration
@pytest.mark.usefixtures("dd_environment")
def test_check_with_filters(aggregator):
    # type: (AggregatorStub) -> None
    check = MarklogicCheck('marklogic', {}, [INSTANCE_FILTERS])

    check.check(INSTANCE_FILTERS)

    _assert_metrics(aggregator, COMMON_TAGS)

    # Resource filter only
    for metric in STORAGE_HOST_METRICS + RESOURCE_STORAGE_FOREST_METRICS:
        aggregator.assert_metric_has_tag(metric, 'forest_name:Security', count=1)
    for metric in [
        'marklogic.requests.query-count',
        'marklogic.requests.total-requests',
        'marklogic.requests.update-count',
    ]:
        aggregator.assert_metric(metric, tags=COMMON_TAGS + ['server_name:Admin', 'group_name:Default'], count=1)

    aggregator.assert_all_metrics_covered()

    # Service checks
    _assert_service_checks(aggregator, COMMON_TAGS)

    aggregator.assert_no_duplicate_all()


@pytest.mark.integration
@pytest.mark.usefixtures('dd_environment')
def test_metadata_integration(aggregator, datadog_agent):
    # type: (AggregatorStub, Any) -> None
    c = MarklogicCheck('marklogic', {}, [INSTANCE])
    c.check_id = 'test:123'
    c.check(INSTANCE)

    parsed_version = version.parse(MARKLOGIC_VERSION)
    version_metadata = {
        'version.scheme': 'marklogic',
        'version.major': str(parsed_version.major),
        'version.minor': str(parsed_version.minor),
        'version.patch': str(parsed_version.post),
        'version.raw': MARKLOGIC_VERSION,
    }

    datadog_agent.assert_metadata('test:123', version_metadata)
    datadog_agent.assert_metadata_count(len(version_metadata))

    # Service checks
    _assert_service_checks(aggregator, COMMON_TAGS)


@pytest.mark.e2e
def test_e2e(dd_agent_check):
    # type: (Any) -> None
    aggregator = dd_agent_check(INSTANCE, rate=True)

    _assert_metrics(aggregator, COMMON_TAGS)

    aggregator.assert_all_metrics_covered()

    # Service checks
    _assert_service_checks(aggregator, COMMON_TAGS, count=2)


def test_submit_health_service_checks(aggregator, caplog):
    # type: (AggregatorStub, Any) -> None
    check = MarklogicCheck('marklogic', {}, [INSTANCE])

    health_mocked_data = {
        'cluster-health-report': [
            {
                "state": "info",
                "resource-type": "database",
                "resource-name": "Security",
                "code": "HEALTH-DATABASE-NO-BACKUP",
                "message": "Database has never been backed up.",
            },
            {'resource-type': 'database', 'resource-name': 'Fab', 'code': 'UNKNOWN'},
        ]
    }

    check.resources = [
        {'id': '255818103205892753', 'type': 'database', 'name': 'Security', 'uri': "/databases/Security"},
        {'id': '5004266825873163057', 'type': 'database', 'name': 'Fab', 'uri': "/databases/Fab"},
        {'id': '16024526243775340149', 'type': 'forest', 'name': 'Modules', 'uri': "/forests/Modules"},
        {'id': '17254568917360711355', 'type': 'forest', 'name': 'Extensions', 'uri': "/forests/Extensions"},
    ]

    # If there is no error
    with mock.patch('datadog_checks.marklogic.api.MarkLogicApi.get_health', return_value=health_mocked_data):
        check.submit_health_service_checks()

        aggregator.assert_service_check(
            'marklogic.database.health',
            MarklogicCheck.OK,
            tags=['foo:bar', 'database_name:Security'],
            message='HEALTH-DATABASE-NO-BACKUP (info): Database has never been backed up.',
            count=1,
        )
        aggregator.assert_service_check(
            'marklogic.database.health',
            MarklogicCheck.UNKNOWN,
            tags=['foo:bar', 'database_name:Fab'],
            message='UNKNOWN (unknown): No message.',
            count=1,
        )
        aggregator.assert_service_check(
            'marklogic.forest.health', MarklogicCheck.OK, tags=['foo:bar', 'forest_name:Modules'], message=None, count=1
        )
        aggregator.assert_service_check(
            'marklogic.forest.health',
            MarklogicCheck.OK,
            tags=['foo:bar', 'forest_name:Extensions'],
            message=None,
            count=1,
        )

    aggregator.reset()
    caplog.clear()

    # If the user doesn't have enough permissions
    with mock.patch(
        'datadog_checks.marklogic.api.MarkLogicApi.get_health', return_value={'code': 'HEALTH-CLUSTER-ERROR'}
    ):
        check.submit_health_service_checks()

        assert "The user needs `manage-admin` permission to monitor databases health." in caplog.text

    aggregator.reset()
    caplog.clear()

    # If MarkLogic can't be reached
    with mock.patch('datadog_checks.marklogic.api.MarkLogicApi.get_health', side_effect=Exception("exception")):
        check.submit_health_service_checks()

        assert "Failed to monitor databases health" in caplog.text
