#!/usr/bin/python3

import difflib
import os
import re
import sys

import ssg.xml
from ssg.constants import FIX_TYPE_TO_SYSTEM


class StandardContentDiffer(object):

    def __init__(self, old_content, new_content, rule_id, show_diffs, rule_diffs, only_rules, output_dir):
        self.old_content = old_content
        self.new_content = new_content

        self.rule_id = rule_id
        self.show_diffs = show_diffs
        self.rule_diffs = rule_diffs
        self.only_rules = only_rules

        self.check_system_map = {
            "OVAL": {"uri": ssg.constants.oval_namespace, "comp_func": self.compare_ovals},
            "OCIL": {"uri": ssg.constants.ocil_cs, "comp_func": self.compare_ocils}
        }

        self.output_dir = output_dir
        if self.rule_diffs:
            self._ensure_output_dir_exists()

    def _ensure_output_dir_exists(self):
        if os.path.exists(self.output_dir):
            if not os.path.isdir(self.output_dir):
                print("Output path '%s' exists and it is not a directory." % self.output_dir)
                sys.exit(1)
        else:
            os.mkdir(self.output_dir)

    def output_diff(self, rule_id, diff, mode="a"):
        if not diff:
            return

        if self.rule_diffs:
            with open("%s/%s" % (self.output_dir, rule_id), mode) as f:
                f.write(diff)
        else:
            print(diff)

    def _get_rules_to_compare(self, benchmark):
        rule_to_find = self.rule_id
        if self.rule_id:
            if not self.rule_id.startswith(ssg.constants.OSCAP_RULE):
                rule_to_find = ssg.constants.OSCAP_RULE + self.rule_id
        rules = benchmark.find_rules(rule_to_find)
        return rules

    def compare_rules(self, old_benchmark, new_benchmark):
        missing_rules = []
        try:
            rules_in_old_benchmark = self._get_rules_to_compare(old_benchmark)
        except ValueError as e:
            print(str(e))
            return

        for old_rule in rules_in_old_benchmark:
            rule_id = old_rule.get_attr("id")
            new_rule = new_benchmark.find_rule(rule_id)
            if new_rule is None:
                missing_rules.append(rule_id)
                print("%s is missing in new datastream." % (rule_id))
                continue
            if self.only_rules:
                continue
            self.compare_rule(old_rule, new_rule)
            self.compare_platforms(old_rule, new_rule,
                                   old_benchmark, new_benchmark)

    def compare_rule(self, old_rule, new_rule):
        self.compare_rule_texts(old_rule, new_rule)
        self.compare_checks(old_rule, new_rule, "OVAL")
        self.compare_checks(old_rule, new_rule, "OCIL")
        for remediation_type in FIX_TYPE_TO_SYSTEM.keys():
            self.compare_remediations(old_rule, new_rule, remediation_type)

    def _get_list_of_platforms(self, cpe_platforms):
        cpe_list = []
        if len(cpe_platforms) == 0:
            print("Platform {0} not defined in platform specification".format(idref))
            return cpe_list
        elif len(cpe_platforms) > 1:
            print("Platform {0} defined more than once".format(idref))
            for cpe_p in cpe_platforms:
                ET.dump(cpe_p)
        for cpe_platform in cpe_platforms:
            fact_refs = cpe_platform.find_all_fact_ref_elements()
            for fact_ref in fact_refs:
                cpe_list.append(fact_ref.get("name"))
        return cpe_list

    def compare_platforms(self, old_rule, new_rule, old_benchmark, new_benchmark):
        rule_id = old_rule.get_attr("id")
        entries = [{
                "benchmark": old_benchmark,
                "rule": old_rule,
                "cpe": []
            }, {
                "benchmark": new_benchmark,
                "rule": new_rule,
                "cpe": []
            }]

        for entry in entries:
            for platform in entry["rule"].get_all_platform_elements():
                idref = platform.get("idref")
                if idref.startswith("#"):
                    cpe_platforms = entry["benchmark"].find_all_cpe_platforms(idref)
                    entry["cpe"] += self._get_list_of_platforms(cpe_platforms)
                else:
                    entry["cpe"].append(idref)

        if entries[0]["cpe"] != entries[1]["cpe"]:
            print("Platform has been changed for rule '{0}'".format(rule_id))

            if self.show_diffs:
                diff = self.generate_diff_text("\n".join(entries[0]["cpe"])+"\n",
                                               "\n".join(entries[1]["cpe"])+"\n",
                                               fromfile=rule_id, tofile=rule_id)
                self.output_diff(rule_id, diff)

    def compare_rule_texts(self, old_rule, new_rule):
        old_rule_text = old_rule.join_text_elements()
        new_rule_text = new_rule.join_text_elements()

        if old_rule_text == new_rule_text:
            return

        rule_id = old_rule.get_attr("id")

        print(
            "New content has different text for rule '%s'." % (rule_id))

        if self.show_diffs:
            diff = self.generate_diff_text(old_rule_text, new_rule_text,
                                           fromfile=rule_id, tofile=rule_id)

            self.output_diff(rule_id, diff, mode="w")

    def compare_check_ids(self, system, rule_id, old_check_id, new_check_id):
        if old_check_id != new_check_id:
            print(
                "%s definition ID for rule '%s' has changed from "
                "'%s' to '%s'." % (
                    system, rule_id, old_check_id, new_check_id)
            )

    def compare_check_file_names(self, system, rule_id,
                                 old_check_file_name, new_check_file_name):
        if old_check_file_name != new_check_file_name:
            print(
                "%s definition file for rule '%s' has changed from "
                "'%s' to '%s'." % (
                    system, rule_id, old_check_file_name, new_check_file_name)
            )

    def get_check_docs(self, system, old_check_file_name, new_check_file_name):
        try:
            old_check_doc = self.old_content.components.get(system)[old_check_file_name]
        except KeyError:
            print(
                "Rule '%s' points to '%s' which isn't a part of the "
                "old datastream" % (rule_id, old_check_file_name))
            old_check_doc = None
        try:
            new_check_doc = self.new_content.components.get(system)[new_check_file_name]
        except KeyError:
            print(
                "Rule '%s' points to '%s' which isn't a part of the "
                "new datastream" % (rule_id, new_check_file_name))
            new_check_doc = None
        return old_check_doc, new_check_doc

    def compare_checks(self, old_rule, new_rule, system):
        check_system_uri = self.check_system_map[system]["uri"]
        old_check = old_rule.get_check_element(check_system_uri)
        new_check = new_rule.get_check_element(check_system_uri)
        rule_id = old_rule.get_attr("id")
        if (old_check is None and new_check is not None):
            print("New datastream adds %s for rule '%s'." % (system, rule_id))
        elif (old_check is not None and new_check is None):
            print(
                "New datastream is missing %s for rule '%s'." % (system, rule_id))
        elif (old_check is not None and new_check is not None):
            old_check_content_ref = old_rule.get_check_content_ref_element(old_check)
            new_check_content_ref = new_rule.get_check_content_ref_element(new_check)
            old_check_id = old_check_content_ref.get("name")
            new_check_id = new_check_content_ref.get("name")
            old_check_file_name = old_check_content_ref.get("href")
            new_check_file_name = new_check_content_ref.get("href")

            self.compare_check_ids(system, rule_id, old_check_id, new_check_id)
            self.compare_check_file_names(system, rule_id,
                                          old_check_file_name, new_check_file_name)

            if (self.show_diffs and
               rule_id != "xccdf_org.ssgproject.content_rule_security_patches_up_to_date"):

                old_check_doc, new_check_doc = self.get_check_docs(system, old_check_file_name,
                                                                   new_check_file_name)
                if not old_check_doc or not new_check_doc:
                    return

                self.check_system_map[system]["comp_func"](old_check_doc, old_check_id,
                                                           new_check_doc, new_check_id, rule_id)

    def compare_ovals(self, old_oval_def_doc, old_oval_def_id,
                      new_oval_def_doc, new_oval_def_id, rule_id):
        old_def = old_oval_def_doc.find_oval_definition(old_oval_def_id)
        new_def = new_oval_def_doc.find_oval_definition(new_oval_def_id)
        old_els = old_def.get_elements()
        new_els = new_def.get_elements()

        old_els_text = self.serialize_elements(old_els)
        new_els_text = self.serialize_elements(new_els)
        diff = self.generate_diff_text(old_els_text, new_els_text,
                                       fromfile=old_oval_def_id, tofile=new_oval_def_id)

        print("OVAL for rule '%s' differs." % (rule_id))
        self.output_diff(rule_id, diff)

    def compare_ocils(self, old_ocil_doc, old_ocil_id, new_ocil_doc, new_ocil_id, rule_id):
        try:
            old_question = old_ocil_doc.find_boolean_question(old_ocil_id)
            new_question = new_ocil_doc.find_boolean_question(new_ocil_id)
        except ValueError as e:
            print("Rule '%s' OCIL can't be found: %s" % (rule_id, str(e)))
            return
        diff = self.generate_diff_text(old_question, new_question,
                                       fromfile=old_ocil_id, tofile=new_ocil_id)

        print("OCIL for rule '%s' differs." % rule_id)
        self.output_diff(rule_id, diff)

    def compare_remediations(self, old_rule, new_rule, remediation_type):
        system = FIX_TYPE_TO_SYSTEM[remediation_type]
        old_fix = old_rule.get_fix_element(system)
        new_fix = new_rule.get_fix_element(system)
        rule_id = old_rule.get_attr("id")
        if (old_fix is None and new_fix is not None):
            print("New datastream adds %s remediation for rule '%s'." % (
                remediation_type, rule_id))
        elif (old_fix is not None and new_fix is None):
            print("New datastream is missing %s remediation for rule '%s'." % (
                remediation_type, rule_id))
        elif (old_fix is not None and new_fix is not None):
            self._compare_fix_elements(
                old_fix, new_fix, remediation_type, rule_id)

    def _compare_fix_elements(self, old_fix, new_fix, remediation_type, rule_id):
        old_fix_id = old_fix.get("id")
        new_fix_id = new_fix.get("id")
        if old_fix_id != new_fix_id:
            print(
                "%s remediation ID for rule '%s' has changed from "
                "'%s' to '%s'." % (
                    remediation_type, rule_id, old_fix_id, new_fix_id)
            )
        if self.show_diffs:
            old_fix_text = "".join(old_fix.itertext())
            new_fix_text = "".join(new_fix.itertext())
            diff = self.generate_diff_text(old_fix_text, new_fix_text,
                                           fromfile=rule_id, tofile=rule_id)

            print("%s remediation for rule '%s' differs." % (remediation_type, rule_id))
            self.output_diff(rule_id, diff)

    def generate_diff_text(self, old_r, new_r,
                           fromfile="old datastream", tofile="new datastream", n=3):
        if old_r != new_r:
            diff = "".join(difflib.unified_diff(
                old_r.splitlines(keepends=True), new_r.splitlines(keepends=True),
                fromfile=fromfile, tofile=tofile, n=n))
            return diff
        return None

    def serialize_elements(self, elements):
        text = ""
        for thing, atrribute in elements:
            text += "%s %s\n" % (thing, atrribute)
        return text


class StigContentDiffer(StandardContentDiffer):

    def __init__(self, old_content, new_content, rule_id, show_diffs, rule_diffs, only_rules, output_dir):
        super(StigContentDiffer, self).__init__(old_content, new_content,
                                                rule_id, show_diffs, rule_diffs, only_rules, output_dir)

    def get_stig_rule_SV(self, rule_id):
        stig_rule_id = re.search(r'(SV-\d+)r\d+_rule', rule_id)
        if not stig_rule_id:
            print("The rule '%s' doesn't have the usual STIG format: 'SV-XXXXXXrXXXXXX_rule.\n"
                  "Please make sure the input contents are DISA STIG Benchmarks." % rule_id)
            sys.exit(1)
        return stig_rule_id.group(1)

    def compare_rules(self, old_benchmark, new_benchmark):
        missing_rules = []
        try:
            rules_in_old_benchmark = self._get_rules_to_compare(old_benchmark)
            rules_in_new_benchmark = self._get_rules_to_compare(new_benchmark)
        except ValueError as e:
            print(str(e))
            return

        # The rules in STIG Benchmarks will have their IDS changed whenever there is an update.
        # However, only the release number changes, the SV number stays the same.
        # This creates map the SV numbers to their equivalent full IDs in the new Benchmark.
        new_rule_mapping = {self.get_stig_rule_SV(rule.get_attr("id")): rule.get_attr("id")
                            for rule in rules_in_new_benchmark}

        for old_rule in rules_in_old_benchmark:
            rule_id = new_rule_mapping[self.get_stig_rule_SV(old_rule.get_attr("id"))]
            new_rule = new_benchmark.find_rule(rule_id)
            if new_rule is None:
                missing_rules.append(rule_id)
                print("%s is missing in new datastream." % (rule_id))
                continue
            if self.only_rules:
                continue
            self.compare_rule(old_rule, new_rule)
            self.compare_platforms(old_rule, new_rule,
                                   old_benchmark, new_benchmark)

    def compare_rule_texts(self, old_rule, new_rule):
        old_rule_text = old_rule.join_text_elements()
        new_rule_text = new_rule.join_text_elements()

        if old_rule_text == new_rule_text:
            return

        stig_id = new_rule.get_version_element()
        print(
            "New content has different text for '%s'." % (stig_id.text))

        if self.show_diffs:
            diff = self.generate_diff_text(old_rule_text, new_rule_text,
                                           fromfile=stig_id.text, tofile=stig_id.text, n=200)
            self.output_diff(stig_id.text, diff)
