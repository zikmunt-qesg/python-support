#!/usr/bin/env python
# -*- coding: utf-8 -*-

from jip import commands
from jip.maven import Artifact
from .const import API, _artifactName
from typing import List
import os


class _ArtifactClsf(Artifact):
    def to_maven_name(self, ext):
        if self.classifier is None or ext == "pom":
            return super().to_maven_name(ext)
        else:
            group = self.group.replace('.', '/')
            return "%s/%s/%s/%s-%s-%s.%s" % (group, self.artifact, self.version, self.artifact,
                                             self.version, self.classifier, ext)

    def to_maven_snapshot_name(self, ext):
        if self.classifier is None or ext == "pom":
            return super().to_maven_snapshot_name(ext)
        else:
            group = self.group.replace('.', '/')
            version_wo_snapshot = self.version.replace('-SNAPSHOT', '')
            return "%s/%s/%s/%s-%s-%s-%s-%s.%s" % (group, self.artifact, self.version, self.artifact,
                                                   version_wo_snapshot,
                                                   self.timestamp, self.build_number, self.classifier, ext)

    def __init__(self, group, artifact, version=None, classifier=None):
        super().__init__(group, artifact, version)
        self.classifier = classifier


# JIP 코드 참조하여 변경함.
def _find_pom(artifact):
    """ find pom and repos contains pom """
    # lookup cache first
    if commands.cache_manager.is_artifact_in_cache(artifact):
        pom = commands.cache_manager.get_artifact_pom(artifact)
        return pom, commands.cache_manager.as_repos()
    else:
        for repos in commands.repos_manager.repos:
            pom = repos.download_pom(artifact)
            # find the artifact
            if pom is not None:
                commands.cache_manager.put_artifact_pom(artifact, pom)
                return pom, repos
        return None


# JIP 코드 참조하여 변경함.
def _resolve_artifacts_modified(artifacts, exclusions=[]):
    # download queue
    download_list = []

    # dependency_set contains artifact objects to resolve
    dependency_set = set()

    for a in artifacts:
        dependency_set.add(a)

    while len(dependency_set) > 0:
        artifact = dependency_set.pop()

        if not any(map(artifact.is_same_artifact, exclusions)):
            if commands.index_manager.is_same_installed(artifact)\
                    and artifact not in download_list:
                continue

            pominfo = _find_pom(artifact)
            if pominfo is None:
                commands.logger.error("[Error] Artifact not found: %s", artifact)
                raise Exception()

            if not commands.index_manager.is_installed(artifact):
                pom, repos = pominfo

                # repos.download_jar(artifact, get_lib_path())
                artifact.repos = repos

                download_list.append(artifact)
                commands.index_manager.add_artifact(artifact)

                pom_obj = commands.Pom(pom)
                for r in pom_obj.get_repositories():
                    commands.repos_manager.add_repos(*r)

                more_dependencies = pom_obj.get_dependencies()
                for d in more_dependencies:
                    d.exclusions.extend(artifact.exclusions)
                    if not commands.index_manager.is_same_installed(d):
                        dependency_set.add(d)

    return download_list


initialized = False
not_assembly = [API.EUNJEON, API.KOMORAN, API.TWITTER]


def initialize(packages=[API.EUNJEON, API.KKMA],
               version="1.9.0",
               java_options="-Xmx4g"):
    """
    초기화 함수. 필요한 Java library를 다운받습니다.

    :param List[API] packages: 사용할 분석기 API의 목록. (기본값: [API.EUNJEON, API.KKMA])
    :param str version: 사용할 분석기의 버전. (기본값: "1.9.0")
    :param str java_options: 자바 JVM option (기본값: "-Xmx4g")
    :raise Exception: JVM이 2회 이상 초기화 될때 Exception.
    """
    global initialized, not_assembly
    if not initialized:
        import jnius_config
        classpaths = []
        java_options = java_options.split(" ")
        jnius_config.add_options(*java_options)
        initialized = True

        deps = [_ArtifactClsf('kr.bydelta', 'koalanlp-%s_2.12' % _artifactName(pack), version,
                              None if pack in not_assembly else "assembly") for pack in packages]
        exclusions = [_ArtifactClsf('com.jsuereth', 'sbt-pgp', '1.1.0')]

        commands.repos_manager.add_repos('maven-central', 'http://central.maven.org/maven2/', 'remote')
        commands.repos_manager.add_repos('jitpack.io', 'https://jitpack.io/', 'remote')

        down_list = _resolve_artifacts_modified(deps, exclusions=exclusions)

        for artifact in down_list:
            local_path = commands.cache_manager.get_jar_path(artifact)
            if artifact.repos != commands.cache_manager.as_repos():
                artifact.repos.download_jar(artifact, local_path)
            classpaths.append(os.path.join(local_path, artifact.to_jip_name()))

        commands.pool.join()
        commands.logger.info("Initialization procedure is completed.")
        jnius_config.add_classpath(*classpaths)
    else:
        raise Exception("JVM cannot be initialized more than once!")
