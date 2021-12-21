# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Kubeflow Pipelines based implementation of TFX components.
These components are lightweight wrappers around the KFP DSL's ContainerOp,
and ensure that the container gets called with the right set of input
arguments. It also ensures that each component exports named output
attributes that are consistent with those provided by the native TFX
components, thus ensuring that both types of pipeline definitions are
compatible.
Note: This requires Kubeflow Pipelines SDK to be installed.
"""
import json
from typing import Dict, List, Set

from google.protobuf import json_format
from kfp import dsl
from kubernetes import client as k8s_client
from tfx.dsl.components.base import base_component as tfx_base_component
from tfx.orchestration import data_types
from tfx.proto.orchestration import pipeline_pb2

from zenml.artifact_stores import LocalArtifactStore
from zenml.constants import ENV_ZENML_PREVENT_PIPELINE_EXECUTION
from zenml.core.repo import Repository
from zenml.integrations.kubeflow.orchestrators import kubeflow_utils as utils
from zenml.metadata_stores import SQLiteMetadataStore
from zenml.utils import source_utils

CONTAINER_ENTRYPOINT_COMMAND = [
    "python",
    "-m",
    "zenml.integrations.kubeflow.container_entrypoint",
]


def _encode_runtime_parameter(param: data_types.RuntimeParameter) -> str:
    """Encode a runtime parameter into a placeholder for value substitution."""
    if param.ptype is int:
        type_enum = pipeline_pb2.RuntimeParameter.INT  # type: ignore[attr-defined] # noqa
    elif param.ptype is float:
        type_enum = pipeline_pb2.RuntimeParameter.DOUBLE  # type: ignore[attr-defined] # noqa
    else:
        type_enum = pipeline_pb2.RuntimeParameter.STRING  # type: ignore[attr-defined] # noqa
    type_str = pipeline_pb2.RuntimeParameter.Type.Name(type_enum)  # type: ignore[attr-defined] # noqa
    return f"{param.name}={type_str}:{str(dsl.PipelineParam(name=param.name))}"


def _get_input_artifact_type_mapping(
    step_component: tfx_base_component.BaseComponent,
) -> Dict[str, str]:
    """Gets artifact classes for each component input.

    Args:
        step_component: The component for which the mapping should be created.

    Returns:
        A dictionary mapping component input names to resolved artifact classes.
    """
    return {
        input_name: source_utils.resolve_class(channel.type)
        for input_name, channel in step_component.spec.inputs.items()
    }


class KubeflowComponent:
    """Base component for all Kubeflow pipelines TFX components.
    Returns a wrapper around a KFP DSL ContainerOp class, and adds named output
    attributes that match the output names for the corresponding native TFX
    components.
    """

    def __init__(
        self,
        component: tfx_base_component.BaseComponent,
        depends_on: Set[dsl.ContainerOp],
        image: str,
        tfx_ir: pipeline_pb2.Pipeline,  # type: ignore[valid-type]
        pod_labels_to_attach: Dict[str, str],
        step_module: str,
        step_function_name: str,
        runtime_parameters: List[data_types.RuntimeParameter],
        metadata_ui_path: str = "/mlpipeline-ui-metadata.json",
    ):
        """Creates a new Kubeflow-based component.
        This class essentially wraps a dsl.ContainerOp construct in Kubeflow
        Pipelines.
        Args:
          component: The logical TFX component to wrap.
          depends_on: The set of upstream KFP ContainerOp components that this
            component will depend on.
          image: The container image to use for this component.
          tfx_ir: The TFX intermedia representation of the pipeline.
          pod_labels_to_attach: Dict of pod labels to attach to the GKE pod.
          runtime_parameters: Runtime parameters of the pipeline.
          metadata_ui_path: File location for metadata-ui-metadata.json file.
        """

        utils.replace_placeholder(component)
        input_artifact_type_mapping = _get_input_artifact_type_mapping(
            component
        )

        arguments = [
            "--node_id",
            component.id,
            "--tfx_ir",
            json_format.MessageToJson(tfx_ir),
            "--metadata_ui_path",
            metadata_ui_path,
            "--step_module",
            step_module,
            "--step_function_name",
            step_function_name,
            "--input_artifact_types",
            json.dumps(input_artifact_type_mapping),
            "--run_name",
            "{{workflow.annotations.pipelines.kubeflow.org/run_name}}",
        ]

        for param in runtime_parameters:
            arguments.append("--runtime_parameter")
            arguments.append(_encode_runtime_parameter(param))

        repo = Repository()
        is_local_artifact_store = isinstance(
            repo.get_active_stack().artifact_store, LocalArtifactStore
        )
        is_local_metadata_store = isinstance(
            repo.get_active_stack().metadata_store, SQLiteMetadataStore
        )

        volumes: Dict[str, k8s_client.V1Volume] = {}

        if is_local_artifact_store or is_local_metadata_store:
            # Only mount the local filesystem if the user has specified a
            # local artifact or metadata store
            local_store_path = repo.service.get_serialization_dir()
            host_path = k8s_client.V1HostPathVolumeSource(
                path=local_store_path, type="Directory"
            )
            volumes[local_store_path] = k8s_client.V1Volume(
                name="local-store", host_path=host_path
            )

        self.container_op = dsl.ContainerOp(
            name=component.id,
            command=CONTAINER_ENTRYPOINT_COMMAND,
            image=image,
            arguments=arguments,
            output_artifact_paths={
                "mlpipeline-ui-metadata": metadata_ui_path,
            },
            pvolumes=volumes,
        )

        for op in depends_on:
            self.container_op.after(op)

        self.container_op.container.add_env_variable(
            k8s_client.V1EnvVar(
                name=ENV_ZENML_PREVENT_PIPELINE_EXECUTION, value="True"
            )
        )

        for k, v in pod_labels_to_attach.items():
            self.container_op.add_pod_label(k, v)