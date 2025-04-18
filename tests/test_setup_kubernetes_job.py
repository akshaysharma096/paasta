from typing import Sequence

import mock
from kubernetes.client import V1Deployment
from kubernetes.client import V1StatefulSet
from pytest import raises

from paasta_tools.kubernetes.application.controller_wrappers import Application
from paasta_tools.kubernetes_tools import InvalidKubernetesConfig
from paasta_tools.kubernetes_tools import KubeDeployment
from paasta_tools.setup_kubernetes_job import create_application_object
from paasta_tools.setup_kubernetes_job import main
from paasta_tools.setup_kubernetes_job import parse_args
from paasta_tools.setup_kubernetes_job import setup_kube_deployments
from paasta_tools.utils import NoConfigurationForServiceError
from paasta_tools.utils import NoDeploymentsAvailable


def test_parse_args():
    with mock.patch(
        "paasta_tools.setup_kubernetes_job.argparse", autospec=True
    ) as mock_argparse:
        assert parse_args() == mock_argparse.ArgumentParser.return_value.parse_args()


def test_main():
    with mock.patch(
        "paasta_tools.setup_kubernetes_job.metrics_lib.get_metrics_interface",
        autospec=True,
    ) as mock_get_metrics_interface, mock.patch(
        "paasta_tools.setup_kubernetes_job.parse_args", autospec=True
    ) as mock_parse_args, mock.patch(
        "paasta_tools.setup_kubernetes_job.KubeClient", autospec=True
    ) as mock_kube_client, mock.patch(
        "paasta_tools.setup_kubernetes_job.ensure_namespace", autospec=True
    ) as mock_ensure_namespace, mock.patch(
        "paasta_tools.setup_kubernetes_job.setup_kube_deployments", autospec=True
    ) as mock_setup_kube_deployments:
        mock_setup_kube_deployments.return_value = True
        mock_metrics_interface = mock_get_metrics_interface.return_value
        with raises(SystemExit) as e:
            main()
        assert e.value.code == 0
        assert mock_ensure_namespace.called
        mock_setup_kube_deployments.assert_called_with(
            kube_client=mock_kube_client.return_value,
            service_instances=mock_parse_args.return_value.service_instance_list,
            cluster=mock_parse_args.return_value.cluster,
            soa_dir=mock_parse_args.return_value.soa_dir,
            rate_limit=mock_parse_args.return_value.rate_limit,
            metrics_interface=mock_metrics_interface,
        )
        mock_setup_kube_deployments.return_value = False
        with raises(SystemExit) as e:
            main()
        assert e.value.code == 1


def test_setup_kube_deployment_invalid_job_name():
    with mock.patch(
        "paasta_tools.setup_kubernetes_job.create_application_object", autospec=True
    ) as mock_create_application_object, mock.patch(
        "paasta_tools.setup_kubernetes_job.list_all_deployments", autospec=True
    ) as mock_list_all_deployments, mock.patch(
        "paasta_tools.setup_kubernetes_job.log", autospec=True
    ):
        mock_client = mock.Mock()
        mock_list_all_deployments.return_value = [
            KubeDeployment(
                service="kurupt",
                instance="f_m",
                git_sha="",
                image_version=None,
                config_sha="",
                replicas=0,
            )
        ]
        mock_service_instances = ["kuruptf_m"]
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )
        assert mock_create_application_object.call_count == 0


def test_create_application_object():
    with mock.patch(
        "paasta_tools.setup_kubernetes_job.load_kubernetes_service_config_no_cache",
        autospec=True,
    ) as mock_load_kubernetes_service_config_no_cache, mock.patch(
        "paasta_tools.setup_kubernetes_job.load_system_paasta_config", autospec=True
    ), mock.patch(
        "paasta_tools.kubernetes.application.controller_wrappers.Application.load_local_config",
        autospec=True,
    ), mock.patch(
        "paasta_tools.kubernetes.application.controller_wrappers.DeploymentWrapper",
        autospec=True,
    ) as mock_deployment_wrapper, mock.patch(
        "paasta_tools.kubernetes.application.controller_wrappers.StatefulSetWrapper",
        autospec=True,
    ) as mock_stateful_set_wrapper:
        mock_kube_client = mock.Mock()
        mock_deploy = mock.MagicMock(spec=V1Deployment)
        service_config = mock.MagicMock()
        mock_load_kubernetes_service_config_no_cache.return_value = service_config
        service_config.format_kubernetes_app.return_value = mock_deploy

        # Create DeploymentWrapper
        create_application_object(
            kube_client=mock_kube_client,
            service="kurupt",
            instance="fm",
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )

        mock_deployment_wrapper.assert_called_with(mock_deploy)

        mock_deploy = mock.MagicMock(spec=V1StatefulSet)
        service_config.format_kubernetes_app.return_value = mock_deploy
        # Create StatefulSetWrapper
        create_application_object(
            kube_client=mock_kube_client,
            service="kurupt",
            instance="fm",
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )
        mock_stateful_set_wrapper.assert_called_with(mock_deploy)

        # Create object that is not statefulset/deployment
        with raises(Exception):
            service_config.format_kubernetes_app.return_value = mock.MagicMock()
            create_application_object(
                kube_client=mock_kube_client,
                service="kurupt",
                instance="fm",
                cluster="fake_cluster",
                soa_dir="/nail/blah",
            )

        mock_deployment_wrapper.reset_mock()
        mock_stateful_set_wrapper.reset_mock()
        mock_load_kubernetes_service_config_no_cache.side_effect = (
            NoDeploymentsAvailable
        )
        ret = create_application_object(
            kube_client=mock_kube_client,
            service="kurupt",
            instance="fm",
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )
        assert ret == (True, None)
        assert not mock_deployment_wrapper.called
        assert not mock_stateful_set_wrapper.called

        mock_load_kubernetes_service_config_no_cache.side_effect = (
            NoConfigurationForServiceError
        )
        ret = create_application_object(
            kube_client=mock_kube_client,
            service="kurupt",
            instance="fm",
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )

        assert ret == (False, None)
        assert not mock_deployment_wrapper.called
        assert not mock_stateful_set_wrapper.called

        mock_load_kubernetes_service_config_no_cache.side_effect = None
        mock_load_kubernetes_service_config_no_cache.return_value = mock.Mock(
            format_kubernetes_app=mock.Mock(
                side_effect=InvalidKubernetesConfig(Exception("Oh no!"), "kurupt", "fm")
            )
        )
        ret = create_application_object(
            kube_client=mock_kube_client,
            service="kurupt",
            instance="fm",
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )

        assert ret == (False, None)
        assert not mock_deployment_wrapper.called
        assert not mock_stateful_set_wrapper.called


def test_setup_kube_deployment_create_update():
    fake_create = mock.MagicMock()
    fake_update = mock.MagicMock()
    fake_update_related_api_objects = mock.MagicMock()

    def simple_create_application_object(
        kube_client, service, instance, cluster, soa_dir
    ):
        fake_app = mock.MagicMock(spec=Application)
        fake_app.kube_deployment = KubeDeployment(
            service=service,
            instance=instance,
            git_sha="1",
            image_version="extrastuff-1",
            config_sha="1",
            replicas=1,
        )
        fake_app.create = fake_create
        fake_app.update = fake_update
        fake_app.update_related_api_objects = fake_update_related_api_objects
        fake_app.item = None
        fake_app.soa_config = None
        fake_app.__str__ = lambda app: "fake_app"
        return True, fake_app

    with mock.patch(
        "paasta_tools.setup_kubernetes_job.create_application_object",
        autospec=True,
        side_effect=simple_create_application_object,
    ) as mock_create_application_object, mock.patch(
        "paasta_tools.setup_kubernetes_job.list_all_deployments", autospec=True
    ) as mock_list_all_deployments, mock.patch(
        "paasta_tools.setup_kubernetes_job.log", autospec=True
    ) as mock_log_obj, mock.patch(
        "paasta_tools.setup_kubernetes_job.metrics_lib.NoMetrics", autospec=True
    ) as mock_no_metrics:
        mock_client = mock.Mock()
        # No instances created
        mock_service_instances: Sequence[str] = []
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )
        assert mock_create_application_object.call_count == 0
        assert fake_update.call_count == 0
        assert fake_update_related_api_objects.call_count == 0
        assert mock_log_obj.info.call_count == 0
        mock_log_obj.info.reset_mock()

        # Create a new instance
        mock_service_instances = ["kurupt.fm"]
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
            metrics_interface=mock_no_metrics,
        )
        assert fake_create.call_count == 1
        assert fake_update.call_count == 0
        assert fake_update_related_api_objects.call_count == 1
        assert mock_no_metrics.emit_event.call_count == 1
        mock_log_obj.info.reset_mock()
        mock_no_metrics.reset_mock()

        # Update when gitsha changed
        fake_create.reset_mock()
        fake_update.reset_mock()
        fake_update_related_api_objects.reset_mock()
        mock_service_instances = ["kurupt.fm"]
        mock_list_all_deployments.return_value = [
            KubeDeployment(
                service="kurupt",
                instance="fm",
                git_sha="2",
                image_version="extrastuff-1",
                config_sha="1",
                replicas=1,
            )
        ]
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
            metrics_interface=mock_no_metrics,
        )

        assert fake_update.call_count == 1
        assert fake_create.call_count == 0
        assert fake_update_related_api_objects.call_count == 1
        mock_no_metrics.emit_event.assert_called_with(
            name="deploy",
            dimensions={
                "paasta_cluster": "fake_cluster",
                "paasta_service": "kurupt",
                "paasta_instance": "fm",
                "deploy_event": "update",
            },
        )
        mock_log_obj.info.reset_mock()
        mock_no_metrics.reset_mock()

        # Update when image_version changed
        fake_create.reset_mock()
        fake_update.reset_mock()
        fake_update_related_api_objects.reset_mock()
        mock_service_instances = ["kurupt.fm"]
        mock_list_all_deployments.return_value = [
            KubeDeployment(
                service="kurupt",
                instance="fm",
                git_sha="1",
                image_version="extrastuff-2",
                config_sha="1",
                replicas=1,
            )
        ]
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )
        assert fake_update.call_count == 1
        assert fake_create.call_count == 0
        assert fake_update_related_api_objects.call_count == 1
        mock_log_obj.info.reset_mock()

        # Update when configsha changed
        fake_create.reset_mock()
        fake_update.reset_mock()
        fake_update_related_api_objects.reset_mock()
        mock_service_instances = ["kurupt.fm"]
        mock_list_all_deployments.return_value = [
            KubeDeployment(
                service="kurupt",
                instance="fm",
                git_sha="1",
                image_version="extrastuff-1",
                config_sha="2",
                replicas=1,
            )
        ]
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )
        assert fake_update.call_count == 1
        assert fake_create.call_count == 0
        assert fake_update_related_api_objects.call_count == 1
        mock_log_obj.info.reset_mock()

        # Update when replica changed
        fake_create.reset_mock()
        fake_update.reset_mock()
        fake_update_related_api_objects.reset_mock()
        mock_service_instances = ["kurupt.fm"]
        mock_list_all_deployments.return_value = [
            KubeDeployment(
                service="kurupt",
                instance="fm",
                git_sha="1",
                image_version="extrastuff-1",
                config_sha="1",
                replicas=2,
            )
        ]
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )
        assert fake_update.call_count == 1
        assert fake_create.call_count == 0
        assert fake_update_related_api_objects.call_count == 1
        mock_log_obj.info.reset_mock()

        # Update one and Create One
        fake_create.reset_mock()
        fake_update.reset_mock()
        fake_update_related_api_objects.reset_mock()
        mock_service_instances = ["kurupt.fm", "kurupt.garage"]
        mock_list_all_deployments.return_value = [
            KubeDeployment(
                service="kurupt",
                instance="garage",
                git_sha="2",
                image_version="extrastuff-1",
                config_sha="2",
                replicas=1,
            )
        ]
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )
        assert fake_update.call_count == 1
        assert fake_create.call_count == 1
        assert fake_update_related_api_objects.call_count == 2
        mock_log_obj.info.reset_mock()

        # Always attempt to update related API objects
        fake_create.reset_mock()
        fake_update.reset_mock()
        fake_update_related_api_objects.reset_mock()
        mock_service_instances = ["kurupt.garage"]
        mock_list_all_deployments.return_value = [
            KubeDeployment(
                service="kurupt",
                instance="garage",
                git_sha="1",
                image_version="extrastuff-1",
                config_sha="1",
                replicas=1,
            )
        ]
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
        )
        assert fake_update.call_count == 0
        assert fake_create.call_count == 0
        assert fake_update_related_api_objects.call_count == 1
        assert mock_log_obj.info.call_args_list[0] == mock.call(
            "fake_app is up-to-date!"
        )


def test_setup_kube_deployments_rate_limit():
    with mock.patch(
        "paasta_tools.setup_kubernetes_job.create_application_object",
        autospec=True,
    ) as mock_create_application_object, mock.patch(
        "paasta_tools.setup_kubernetes_job.list_all_deployments", autospec=True
    ), mock.patch(
        "paasta_tools.setup_kubernetes_job.log", autospec=True
    ) as mock_log_obj:
        mock_client = mock.Mock()
        mock_service_instances = ["kurupt.fm", "kurupt.garage", "kurupt.radio"]
        fake_app = mock.Mock(create=mock.Mock())
        mock_create_application_object.return_value = (True, fake_app)

        # Rate limit: 2 calls allowed
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
            rate_limit=2,
        )
        assert fake_app.create.call_count == 2
        mock_log_obj.info.assert_any_call(
            "Not doing any further updates as we reached the limit (2)"
        )

        # No rate limit
        fake_app.reset_mock()
        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
            rate_limit=0,
        )
        assert fake_app.create.call_count == 3


def test_setup_kube_deployments_skip_malformed_apps():
    with mock.patch(
        "paasta_tools.setup_kubernetes_job.create_application_object",
        autospec=True,
    ) as mock_create_application_object, mock.patch(
        "paasta_tools.setup_kubernetes_job.list_all_deployments", autospec=True
    ), mock.patch(
        "paasta_tools.setup_kubernetes_job.log", autospec=True
    ) as mock_log_obj:
        mock_client = mock.Mock()
        mock_service_instances = ["fake.instance", "mock.instance"]
        fake_app = mock.Mock(create=mock.Mock())
        fake_app.create = mock.Mock(
            side_effect=[Exception("Kaboom!"), mock.Mock(create=mock.Mock())]
        )
        fake_app.__str__ = mock.Mock(return_value="fake_app")
        mock_create_application_object.return_value = (True, fake_app)

        setup_kube_deployments(
            kube_client=mock_client,
            service_instances=mock_service_instances,
            cluster="fake_cluster",
            soa_dir="/nail/blah",
            rate_limit=0,
        )
        assert fake_app.create.call_count == 2
        assert len(mock_log_obj.exception.call_args_list) == 1
        assert mock_log_obj.exception.call_args_list[0] == mock.call(
            "Error while processing: fake_app"
        )
