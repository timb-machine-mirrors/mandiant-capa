# -*- coding: utf-8 -*-
# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import itertools
import collections
from typing import Optional
from dataclasses import dataclass

from capa.rules import Rule, Scope, RuleSet
from capa.engine import FeatureSet, MatchResults
from capa.features.address import NO_ADDRESS
from capa.render.result_document import LibraryFunction, StaticFeatureCounts, DynamicFeatureCounts
from capa.features.extractors.base_extractor import FeatureExtractor, StaticFeatureExtractor, DynamicFeatureExtractor

logger = logging.getLogger(__name__)


@dataclass
class FileCapabilities:
    features: FeatureSet
    matches: MatchResults
    feature_count: int


def find_file_capabilities(
    ruleset: RuleSet, extractor: FeatureExtractor, function_features: FeatureSet
) -> FileCapabilities:
    file_features: FeatureSet = collections.defaultdict(set)

    for feature, va in itertools.chain(extractor.extract_file_features(), extractor.extract_global_features()):
        # not all file features may have virtual addresses.
        # if not, then at least ensure the feature shows up in the index.
        # the set of addresses will still be empty.
        if va:
            file_features[feature].add(va)
        else:
            if feature not in file_features:
                file_features[feature] = set()

    logger.debug("analyzed file and extracted %d features", len(file_features))

    file_features.update(function_features)

    features, matches = ruleset.match(Scope.FILE, file_features, NO_ADDRESS)
    return FileCapabilities(features, matches, len(file_features))


@dataclass
class Capabilities:
    matches: MatchResults
    feature_counts: StaticFeatureCounts | DynamicFeatureCounts
    library_functions: Optional[tuple[LibraryFunction, ...]] = None


def find_capabilities(ruleset: RuleSet, extractor: FeatureExtractor, disable_progress=None, **kwargs) -> Capabilities:
    from capa.capabilities.static import find_static_capabilities
    from capa.capabilities.dynamic import find_dynamic_capabilities

    if isinstance(extractor, StaticFeatureExtractor):
        # for the time being, extractors are either static or dynamic.
        # Remove this assertion once that has changed
        assert not isinstance(extractor, DynamicFeatureExtractor)
        return find_static_capabilities(ruleset, extractor, disable_progress=disable_progress, **kwargs)
    if isinstance(extractor, DynamicFeatureExtractor):
        return find_dynamic_capabilities(ruleset, extractor, disable_progress=disable_progress, **kwargs)

    raise ValueError(f"unexpected extractor type: {extractor.__class__.__name__}")


def has_limitation(rules: list, capabilities: Capabilities | FileCapabilities, is_standalone: bool) -> bool:

    for rule in rules:
        if rule.name not in capabilities.matches:
            continue
        logger.warning("-" * 80)
        for line in rule.meta.get("description", "").split("\n"):
            logger.warning(" %s", line)
        logger.warning(" Identified via rule: %s", rule.name)
        if is_standalone:
            logger.warning(" ")
            logger.warning(" Use -v or -vv if you really want to see the capabilities identified by capa.")
        logger.warning("-" * 80)

        # bail on first file limitation
        return True
    return False


def is_static_limitation_rule(r: Rule) -> bool:
    return r.meta.get("namespace", "") == "internal/limitation/static"


def has_static_limitation(rules: RuleSet, capabilities: Capabilities | FileCapabilities, is_standalone=True) -> bool:
    file_limitation_rules = list(filter(lambda r: is_static_limitation_rule(r), rules.rules.values()))
    return has_limitation(file_limitation_rules, capabilities, is_standalone)


def is_dynamic_limitation_rule(r: Rule) -> bool:
    return r.meta.get("namespace", "") == "internal/limitation/dynamic"


def has_dynamic_limitation(rules: RuleSet, capabilities: Capabilities | FileCapabilities, is_standalone=True) -> bool:
    dynamic_limitation_rules = list(filter(lambda r: is_dynamic_limitation_rule(r), rules.rules.values()))
    return has_limitation(dynamic_limitation_rules, capabilities, is_standalone)
