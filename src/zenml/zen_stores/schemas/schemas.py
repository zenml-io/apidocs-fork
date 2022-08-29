#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""SQL Model Implementations."""

from datetime import datetime
from typing import List
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

from zenml.enums import StackComponentType
from zenml.models.pipeline_models import PipelineRunModel


def _sqlmodel_uuid() -> UUID:
    """Generates a UUID whose hex string does not start with a '0'.

    Returns:
        A UUID whose hex string does not start with a '0'.
    """
    # SQLModel crashes when a UUID hex string starts with '0'
    # (see: https://github.com/tiangolo/sqlmodel/issues/25)
    uuid = uuid4()
    while uuid.hex[0] == "0":
        uuid = uuid4()
    return uuid


# Projects, Repositories


class ProjectSchema(SQLModel, table=True):
    """SQL Model for projects."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)
    name: str
    created_at: datetime = Field(default_factory=datetime.now)


class RepositorySchema(SQLModel, table=True):
    """SQL Model for repositories."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)
    name: str
    project_id: UUID = Field(foreign_key="projectschema.id")
    created_at: datetime = Field(default_factory=datetime.now)


# Users, Teams, Roles


class UserSchema(SQLModel, table=True):
    """SQL Model for users."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)
    name: str
    created_at: datetime = Field(default_factory=datetime.now)


class TeamSchema(SQLModel, table=True):
    """SQL Model for teams."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)
    name: str
    created_at: datetime = Field(default_factory=datetime.now)


class TeamAssignmentSchema(SQLModel, table=True):
    """SQL Model for team assignments."""

    user_id: UUID = Field(primary_key=True, foreign_key="userschema.id")
    team_id: UUID = Field(primary_key=True, foreign_key="teamschema.id")


class RoleSchema(SQLModel, table=True):
    """SQL Model for roles."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)
    name: str
    created_at: datetime = Field(default_factory=datetime.now)


class UserRoleAssignmentSchema(SQLModel, table=True):
    """SQL Model for assigning roles to users for a given project."""

    role_id: UUID = Field(primary_key=True, foreign_key="roleschema.id")
    user_id: UUID = Field(primary_key=True, foreign_key="userschema.id")
    project_id: UUID = Field(primary_key=True, foreign_key="projectschema.id")


class TeamRoleAssignmentSchema(SQLModel, table=True):
    """SQL Model for assigning roles to teams for a given project."""

    role_id: UUID = Field(primary_key=True, foreign_key="roleschema.id")
    team_id: UUID = Field(primary_key=True, foreign_key="teamschema.id")
    project_id: UUID = Field(primary_key=True, foreign_key="projectschema.id")


# Stacks, Stack Components, Flavors


class FlavorSchema(SQLModel, table=True):
    """SQL Model for flavors."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)

    name: str

    # project_id - redundant since repository has this
    repository_id: UUID = Field(foreign_key="repositoryschema.id")
    created_by: UUID = Field(foreign_key="userschema.id")

    type: StackComponentType
    source: str
    git_sha: str
    integration: str

    created_at: datetime = Field(default_factory=datetime.now)


class StackCompositionSchema(SQLModel, table=True):
    """SQL Model for stack definitions.

    Join table between Stacks and StackComponents.
    """

    stack_id: UUID = Field(primary_key=True, foreign_key="stackschema.id")
    component_id: UUID = Field(
        primary_key=True, foreign_key="stackcomponentschema.id"
    )


class StackSchema(SQLModel, table=True):
    """SQL Model for stacks."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)

    name: str

    project_id: UUID = Field(
        foreign_key="projectschema.id", nullable=True
    )  # TODO: Unnullableify this
    owner: UUID = Field(
        foreign_key="userschema.id", nullable=True
    )  # TODO: Unnullableify this

    created_at: datetime = Field(default_factory=datetime.now)

    components: List["StackComponentSchema"] = Relationship(
        back_populates="stack", link_model=StackCompositionSchema
    )


class StackComponentSchema(SQLModel, table=True):
    """SQL Model for stack components."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)

    name: str

    # project_id - redundant since repository of flavor has this
    type: StackComponentType
    flavor_id: UUID = Field(
        foreign_key="flavorschema.id", nullable=True
    )  # TODO: Prefill flavors
    owner: UUID = Field(foreign_key="userschema.id", nullable=True)

    # type - redundant since flavor has this
    configuration: str

    created_at: datetime = Field(default_factory=datetime.now)

    stacks: List["StackSchema"] = Relationship(
        back_populates="components", link_model=StackCompositionSchema
    )


class PipelineSchema(SQLModel, table=True):
    """SQL Model for pipelines."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)

    name: str

    # project_id - redundant since repository has this
    repository_id: UUID = Field(foreign_key="repositoryschema.id")
    created_by: UUID = Field(foreign_key="userschema.id")

    configuration: str
    git_sha: str

    created_at: datetime = Field(default_factory=datetime.now)


class PipelineRunSchema(SQLModel, table=True):
    """SQL Model for pipeline runs."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)

    name: str

    # project_id - redundant since stack/pipeline has this
    stack_id: UUID = Field(foreign_key="stackschema.id")
    pipeline_id: UUID = Field(foreign_key="pipelineschema.id")
    # context_id - TODO ?
    created_by: UUID = Field(foreign_key="userschema.id")

    runtime_configuration: str
    git_sha: str
    zenml_version: str

    created_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_pipeline_run_wrapper(
        cls, wrapper: PipelineRunModel
    ) -> "PipelineRunSchema":
        """Creates a PipelineRunTable from a PipelineRunModel.

        Args:
            wrapper: The PipelineRunModel to create the PipelineRunTable from.

        Returns:
            A PipelineRunTable.
        """
        pass  # TODO

    def to_pipeline_run_wrapper(self) -> PipelineRunModel:
        """Creates a PipelineRunModel from a PipelineRunTable.

        Returns:
            A PipelineRunModel.
        """
        pass  # TODO


class PipelineRunStepSchema(SQLModel, table=True):
    """SQL Model for pipeline run steps."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)

    name: str

    pipeline_run_id: UUID = Field(foreign_key="pipelinerunschema.id")
    # created_by - redundant since run has this

    runtime_configuration: str

    # created_at - redundant since run has this


# MLMD


class MLMDSchema(SQLModel, table=True):
    """SQL Model for MLMD."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)
    project_id: UUID = Field(foreign_key="projectschema.id")
    type: str


class MLMDPropertySchema(SQLModel, table=True):
    """SQL Model for MLMD Properties."""

    id: UUID = Field(primary_key=True, default_factory=_sqlmodel_uuid)
    name: str
    mlmd_id: UUID = Field(foreign_key="mlmdschema.id")
    value: str