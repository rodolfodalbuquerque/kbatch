import pytest
import kubernetes.client

import kbatch_proxy.utils
import kbatch_proxy.main
import kbatch_proxy.patch


@pytest.fixture
def k8s_job() -> kubernetes.client.V1Job:
    job = kubernetes.client.models.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=kubernetes.client.models.V1ObjectMeta(
            name="name",
            generate_name="name-",
            annotations={"foo": "bar"},
            labels={"baz": "qux"},
        ),
        spec=kubernetes.client.V1JobSpec(
            template=kubernetes.client.V1PodTemplateSpec(
                spec=kubernetes.client.V1PodSpec(
                    containers=[
                        kubernetes.client.V1Container(
                            args=["ls", "-lh"],
                            command=None,
                            image="alpine",
                            name="job",
                            env=[
                                kubernetes.client.V1EnvVar(
                                    name="MYENV", value="MYVALUE"
                                )
                            ],
                            resources=kubernetes.client.V1ResourceRequirements(),
                        )
                    ],
                    restart_policy="Never",
                    tolerations=None,
                ),
                metadata=kubernetes.client.V1ObjectMeta(
                    name="test-name-pod",
                    labels={"pod": "label"},
                    annotations={"pod": "annotations"},
                ),
            ),
            backoff_limit=4,
            ttl_seconds_after_finished=300,
        ),
    )
    return job


def test_parse_job(k8s_job: kubernetes.client.V1Job):
    result = kbatch_proxy.utils.parse(k8s_job.to_dict(), kubernetes.client.V1Job)
    assert result == k8s_job

    container = result.spec.template.spec.containers[0]
    assert isinstance(container, kubernetes.client.V1Container)
    assert container.args == ["ls", "-lh"]


def test_patch_job(k8s_job: kubernetes.client.V1Job):
    kbatch_proxy.patch.patch(
        k8s_job, None, annotations={}, labels={}, username="myuser"
    )

    assert k8s_job.metadata.namespace == "myuser"
    assert k8s_job.spec.template.metadata.namespace == "myuser"


@pytest.mark.parametrize(
    "username, expected",
    [
        ("test", "test"),
        ("TEST", "test"),
        ("test123test", "test123test"),
        ("test-test", "test-test"),
        ("taugspurger@microsoft.com", "taugspurger-microsoft-com"),
    ],
)
def test_namespace_for_username(username, expected):
    result = kbatch_proxy.patch.namespace_for_username(username)
    assert result == expected

    result = kbatch_proxy.main.User(name=username, groups=[]).namespace
    assert result == expected


def test_namespace_configmap():
    cm = kubernetes.client.V1ConfigMap(metadata=kubernetes.client.V1ObjectMeta())
    assert cm.metadata.namespace is None
    kbatch_proxy.patch.add_namespace_configmap(cm, "my-namespace")
    assert cm.metadata.namespace == "my-namespace"


@pytest.mark.parametrize("has_init_containers", [True, False])
@pytest.mark.parametrize("has_volumes", [True, False])
def test_add_unzip_init_container(
    k8s_job: kubernetes.client.V1Job, has_init_containers: bool, has_volumes: bool
):
    if has_init_containers:
        k8s_job.spec.template.spec.init_containers = [
            kubernetes.client.V1Container(name="present-container")
        ]

    if has_volumes:
        k8s_job.spec.template.spec.volumes = [
            kubernetes.client.V1Volume(name="present-volume", empty_dir={})
        ]
        k8s_job.spec.template.spec.containers[0].volume_mounts = [
            kubernetes.client.V1VolumeMount(
                name="present-volume", mount_path="/present-volume"
            )
        ]

    kbatch_proxy.patch.add_unzip_init_container(k8s_job)

    n_init_containers = int(has_init_containers) + 1
    assert len(k8s_job.spec.template.spec.init_containers) == n_init_containers

    n_volumes = int(has_volumes) + 2
    assert len(k8s_job.spec.template.spec.volumes) == n_volumes

    n_volume_mounts = int(has_volumes) + 1
    assert (
        len(k8s_job.spec.template.spec.containers[0].volume_mounts) == n_volume_mounts
    )

    # now patch with the actual name
    config_map = kubernetes.client.V1ConfigMap(
        metadata=kubernetes.client.V1ObjectMeta(
            name="actual-name", namespace="my-namespace"
        )
    )
    kbatch_proxy.patch.add_submitted_configmap_name(k8s_job, config_map)
    assert k8s_job.spec.template.spec.volumes[-2].config_map.name == "actual-name"