#!/usr/bin/env python3
"""Healthcare plan cost simulator.

Compares health insurance plans by simulating a year of healthcare
utilization for a family under each plan's cost-sharing rules.

Plan YAML schema (cost_sharing entries)
---------------------------------------
Each service entry under ``cost_sharing.<network>.<service>`` is a mapping
that may contain:

* ``copay`` or ``coinsurance``       One of these is required. ``coinsurance``
                                     is a percentage (e.g. ``10`` = 10%).
* ``deductible_applies``            Whether the deductible must be met before
                                     the plan's cost sharing begins. Defaults
                                     to ``true`` for coinsurance and ``false``
                                     for copays. Plans that differ (e.g. an
                                     HDHP whose ER copay applies only after
                                     the deductible) must set this
                                     explicitly.
* ``waived_if_admitted``            True for ER-style copays that are waived
                                     when the visit results in a hospital
                                     admission. The admission itself is
                                     billed separately as ``hospital_stay``
                                     utilization, so the ER line costs $0.
* ``limit: {max: N}``               Per-member annual covered-occurrence cap
                                     (e.g. skilled nursing facility day
                                     limits). Occurrences are counted per
                                     member across both network levels, and
                                     only covered occurrences count. When a
                                     service declares a limit, it should use
                                     the same value in both network entries;
                                     the engine resolves the cap once (the
                                     in-network entry wins) so results do not
                                     depend on processing order. Beyond the
                                     cap the member pays the full price and
                                     nothing counts toward the deductible or
                                     out-of-pocket max.
* ``max_plan_paid: X``              Allowance benefits (e.g. children's
                                     eyewear up to $150): the plan pays up to
                                     ``X``; the member pays the excess.
                                     Deductibles never apply to allowances,
                                     so ``deductible_applies`` is ignored
                                     here.
* ``counts_toward_oop_max``         Defaults to ``true``. Set ``false`` for
                                     services the plan excludes from the
                                     out-of-pocket maximum (cost sharing
                                     continues even after the OOP max is
                                     met, and never reduces it).

Prescription entries (``prescription_medicine``) map drug tiers to copay or
coinsurance amounts and may additionally contain:

* ``overrides``                     Mapping of drug category (e.g.
                                     ``glp1_weight_loss``, ``preventive``) to
                                     a cost-sharing entry used instead of the
                                     tier amount for drugs in that category.
* ``deductible_applies``,           Plan-wide defaults for prescriptions.
  ``counts_toward_oop_max``          Every tier rule and every category
                                     override inherits them; an override's
                                     own fields take precedence.
* ``generic_substitution: member_pays_difference``
                                     When a non-generic drug is dispensed
                                     although a cheaper generic equivalent
                                     is named, the plan shares cost as if
                                     the generic had been dispensed (at the
                                     generic tier's rate, unless a category
                                     override applies); the member
                                     additionally pays the full price
                                     difference, uncovered.

Utilization YAML schema
-----------------------
Service utilization values may be a plain count (int) or a mapping:

* ``{count: N, admitted: true}``    ``admitted`` activates
                                     ``waived_if_admitted`` rules.

Medication entries may extend ``type`` (tier) and ``frequency`` with:

* ``category``                      Drug category for plan overrides (e.g.
                                     ``glp1_weight_loss``, ``contraceptive``).
* ``network``                       Defaults to ``in_network``.
* ``generic_substitute``            Name of a cheaper equivalent drug listed
                                     in the service prices file; activates
                                     the plan's ``generic_substitution``
                                     rule if one exists.

Out-of-pocket handling: charges for services that are not covered (no
out-of-network benefit, day limits exceeded, generic-substitution price
differences, waived copays) never count toward the deductible or the
out-of-pocket maximum, mirroring how plans treat uncovered services.
"""

import argparse
import yaml

# Constants
FAMILY_SIZE_MAP = {
    1: "employee_only",
    2: "employee_plus_one",
    3: "family",
}
# Constants for file paths
HEALTHCARE_PLANS_PATH = "examples/healthcare_plans.yml"
SERVICE_PRICES_PATH = "examples/service_prices.yml"
UTILIZATION_PATH = "examples/family_utilization.yml"


def load_yaml_file(file_path):
    print(f"Reading: {file_path}")
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def read_healthcare_plans(file_path="healthcare_plans.yml"):
    return load_yaml_file(file_path)


def read_service_prices(file_path="service_prices.yml"):
    return load_yaml_file(file_path)


def read_utilization(file_path="family_utilization.yml"):
    return load_yaml_file(file_path)


class CostSharingBalance:
    """
    Class to manage deductibles and out-of-pocket expenses.
    """
    def __init__(self, member_amount, family_amount, per_member, family_size):
        """
        Initialize a CostSharingBalance object to manage deductibles and out-of-pocket expenses.

        :param member_amount: The individual member's deductible or out-of-pocket amount.
        :param family_amount: The family's deductible or out-of-pocket amount.
        :param per_member: Boolean indicating if the deductible or out-of-pocket limit is per member.
        """
        # Single person family only needs to meet the individual member amount, regardless of per_member rules
        self.family_amount_original = self.family_amount = family_amount if family_size > 1 else member_amount
        self.member_amount_original = self.member_amount = member_amount
        self.per_member = per_member

    def get_balance(self):
        """
        Get the balance of the deductible or out-of-pocket max.

        When the plan rules indicate the balance is tracked per member, we
        return the lesser of the member's balance and the family's balance.
        When either is met, insurance benefits kick in.
        Otherwise, we return the family amount.

        For single person families, we set the family amount to the member amount
        upon initialization, so this doesn't matter.
        """
        if (self.per_member):
            return min(self.member_amount, self.family_amount)
        return self.family_amount


    def subtract_balance(self, expense):
        """
        Subtract an expense from the deductible or out-of-pocket max balance.

        :param expense: The amount of the expense to subtract from the balance.

        If the plan rules track this balance per-member, then the member's balance
        and family balance are both updated. In a single-person family, the
        per_member flag is irrelevant because no other expenses are processed
        after that person's utilization is processed.
        """
        self.family_amount = max(0, self.family_amount - expense)
        self.member_amount = max(0, self.member_amount - expense)

    def reset_member_balance(self):
        """
        Reset the member's deductible or out-of-pocket max balance.
        """
        self.member_amount = self.member_amount_original


class ServiceRule:
    """
    A single service's cost-sharing rule, parsed from plan data.

    Handles the plain copay/coinsurance mechanics as well as plan quirks:
    admission-waived copays, allowance caps, and out-of-pocket-maximum
    exclusions. Occurrence limits are resolved by the plan, not here. See
    the module docstring for the corresponding YAML keys.
    """

    def __init__(self, service, entry):
        if not isinstance(entry, dict) or ("copay" not in entry and "coinsurance" not in entry):
            raise ValueError(
                "Cost-sharing rule for {!r} must be a mapping with a 'copay' or "
                "'coinsurance' key; got {!r}".format(service, entry)
            )
        if "copay" in entry:
            self.sharing_type = "copay"
            self.amount = entry["copay"]
        else:
            self.sharing_type = "coinsurance"
            self.amount = entry["coinsurance"]

        # Deductibles normally apply to coinsurance services but not to copay
        # services. Plans whose copays apply after the deductible (common in
        # high-deductible plans) must say so explicitly.
        self.deductible_applies = bool(
            entry.get("deductible_applies", self.sharing_type == "coinsurance")
        )
        self.waived_if_admitted = bool(entry.get("waived_if_admitted", False))
        self.counts_toward_oop_max = bool(entry.get("counts_toward_oop_max", True))
        self.max_plan_paid = entry.get("max_plan_paid")

    def cost_after_deductible(self, service_price):
        """The member's cost for the service once cost sharing applies."""
        if self.sharing_type == "copay":
            # A copay never exceeds the price of the service itself.
            return min(self.amount, service_price)
        return service_price * (self.amount / 100)


class HealthcarePlan:
    def __init__(
        self,
        name,
        company,
        description,
        network_family,
        contributions,
        HSA_funding,
        cost_sharing,
        out_of_network_coverage,
        plan_deductibles,
        plan_out_of_pocket_max,
        family_size,
    ):
        self.name = name
        self.company = company
        self.description = description
        self.network_family = network_family
        self.contributions = contributions
        self.HSA_funding = HSA_funding
        self.cost_sharing = cost_sharing
        self.out_of_network_coverage = out_of_network_coverage
        self.plan_deductibles = plan_deductibles
        self.plan_out_of_pocket_max = plan_out_of_pocket_max
        self.family_size = family_size

        self.deductibles = {}
        self.out_of_pocket_max = {}
        # Covered occurrences the member being simulated has used so far this
        # year, by service. A single count spans both network levels because
        # occurrence limits are annual per-member caps.
        self.service_occurrences = {}

        for network_type in ["in_network", "out_of_network"]:
            if plan_deductibles.get(network_type):
                self._init_balances(network_type, plan_deductibles, self.deductibles)
            if plan_out_of_pocket_max.get(network_type):
                self._init_balances(network_type, plan_out_of_pocket_max, self.out_of_pocket_max)

    def reset_member_usage(self):
        """Clears the per-member usage counters behind occurrence limits.
        Call before simulating each member's utilization."""
        self.service_occurrences = {}

    def _init_balances(self, network_type: str, plan_balances: dict, balances_dict: dict) -> None:
        """
        Initializes the cost sharing balances for a given network type.

        :param network_type: The type of network to initialize the balances for (in_network or out_of_network)
        :type network_type: str
        :param plan_balances: A dictionary containing the member and family amounts for each network type.
        :type plan_balances: dict
        :param balances_dict: A dictionary to store the cost sharing balances for each network type.
        :type balances_dict: dict

        :return: None
        :rtype: None
        """

        balances_dict[network_type] = CostSharingBalance(
            member_amount=plan_balances[network_type]["member"],
            family_amount=plan_balances[network_type]["family"],
            per_member=plan_balances[network_type].get("per_member", False),
            family_size=self.family_size,
        )

    def calculate_total_premium(self, family_size):
        return self.contributions.get(FAMILY_SIZE_MAP.get(family_size, FAMILY_SIZE_MAP[3]))

    def get_service_rule(self, network_coverage_level, service_type):
        """
        Returns the ServiceRule for a service, or None when the plan has no
        cost-sharing entry for it (the member pays the full price, uncovered).
        """
        entry = self.cost_sharing.get(network_coverage_level, {}).get(service_type)
        if entry is None:
            return None
        return ServiceRule(service_type, entry)

    def _service_limit_max(self, service_type):
        """The per-member annual occurrence cap for a service, resolved
        deterministically so results do not depend on processing order: the
        in-network entry's limit wins, with the out-of-network entry as the
        fallback. Returns None when neither entry declares a limit."""
        for network_coverage_level in ("in_network", "out_of_network"):
            entry = self.cost_sharing.get(network_coverage_level, {}).get(service_type)
            if isinstance(entry, dict):
                limit = entry.get("limit")
                if limit is not None:
                    return limit.get("max") if isinstance(limit, dict) else limit
        return None

    def _balances_for(self, network_coverage_level):
        """Deductible and OOP balances for a network level, falling back to
        in-network balances for plans that combine the two."""
        deductible = self.deductibles.get(network_coverage_level, self.deductibles["in_network"])
        out_of_pocket_max = self.out_of_pocket_max.get(
            network_coverage_level, self.out_of_pocket_max["in_network"]
        )
        return deductible, out_of_pocket_max

    def apply_cost_sharing_service(
        self, network_coverage_level, service_type, service_price,
        service_options=None,
    ):
        """
        Applies cost sharing to a given service price based on the network coverage level and service type.
        This will account for adjustments based on current deductible and out-of-pocket max balances,
        and on how many covered occurrences of the service the current member has already used
        (see `reset_member_usage`).

        Args:
            network_coverage_level (str): The level of network coverage for the service (e.g. in-network or out-of-network)
            service_type (str): The type of service.
            service_price (float): The price of the service before cost sharing.
            service_options (dict): Optional utilization details, e.g. {"admitted": true}.

        Returns:
            float: The price of the service after cost sharing.
        """
        service_options = service_options or {}

        if network_coverage_level == 'out_of_network' and not self.out_of_network_coverage:
            print("Service type {} is not covered out of network".format(service_type))
            print("Member pays full price: {}".format(service_price))
            return service_price

        rule = self.get_service_rule(network_coverage_level, service_type)
        if rule is None:
            print("No coverage for service type {} at network level {}".format(service_type, network_coverage_level))
            print("Member pays full price: {}".format(service_price))
            # This does not count towards the deductible or out-of-pocket max.
            return service_price

        # ER-style copay waived when the visit results in a hospital
        # admission. The admission is billed separately (hospital_stay), so
        # this ER line itself costs the member nothing, regardless of any
        # occurrence limit or cost sharing.
        if rule.waived_if_admitted and service_options.get("admitted"):
            print("Service {} copay waived due to hospital admission".format(service_type))
            return 0.0

        # Occurrence limits (e.g. skilled nursing facility day caps) are annual
        # per-member caps on covered occurrences, counted across both network
        # levels. The limit is resolved once per service (in-network preferred)
        # so results do not depend on processing order. Past the cap the
        # service is not covered at all.
        limit_max = self._service_limit_max(service_type)
        used = self.service_occurrences.get(service_type, 0)
        if limit_max is not None and used >= limit_max:
            print(
                "Service {} occurrence {} exceeds the plan limit of {}; "
                "member pays full price".format(service_type, used + 1, limit_max)
            )
            return service_price
        self.service_occurrences[service_type] = used + 1

        # Allowance benefits (e.g. children's eyewear up to $150): the plan
        # pays up to a fixed amount; the member pays the excess. Deductibles
        # do not apply to allowances.
        if rule.max_plan_paid is not None:
            return self._apply_allowance(rule, service_price, network_coverage_level)

        return self._apply_rule(rule, service_price, network_coverage_level)

    def _apply_allowance(self, rule, service_price, network_coverage_level):
        member_cost = max(0.0, service_price - rule.max_plan_paid)
        if member_cost <= 0:
            return 0.0
        if not rule.counts_toward_oop_max:
            return member_cost
        _, out_of_pocket_max = self._balances_for(network_coverage_level)
        if out_of_pocket_max.get_balance() <= 0:
            return 0.0
        member_cost = min(member_cost, out_of_pocket_max.get_balance())
        out_of_pocket_max.subtract_balance(member_cost)
        return member_cost

    def _prescription_entry(self, network_coverage_level):
        """The plan's prescription benefit at a network level, or None when
        the plan has no pharmacy benefit there."""
        rx_entry = self.cost_sharing.get(network_coverage_level, {}).get("prescription_medicine")
        return rx_entry if isinstance(rx_entry, dict) else None

    def _build_prescription_rule(self, rx_entry, network_coverage_level, tier, category=None):
        """
        Builds the ServiceRule for a prescription from the plan's prescription
        entry: its tier table plus any category override (e.g.
        glp1_weight_loss, preventive).

        Plan-wide prescription settings (`deductible_applies` and
        `counts_toward_oop_max` on the prescription entry) are the defaults
        for every rule built here, whether it comes from a tier or from a
        category override. An override's own fields take precedence.
        """
        rule_entry = {
            key: rx_entry[key]
            for key in ("deductible_applies", "counts_toward_oop_max")
            if key in rx_entry
        }
        override = (rx_entry.get("overrides") or {}).get(category) if category else None
        if override is not None:
            # The override supplies the whole rule, so neither the drug's tier
            # nor the plan's tier table is needed.
            rule_entry.update(override)
            rule_name = category
            return ServiceRule("prescription_medicine[{}]".format(rule_name), rule_entry)

        sharing_type = "copay" if "copay" in rx_entry else "coinsurance" if "coinsurance" in rx_entry else None
        if sharing_type is None:
            raise ValueError(
                "Prescription cost sharing at {} needs a copay or coinsurance "
                "tier table or a category override".format(network_coverage_level)
            )
        tiers = rx_entry[sharing_type]
        if tier not in tiers:
            raise KeyError(
                "Plan has no {} tier {!r} for prescriptions at {}".format(
                    sharing_type, tier, network_coverage_level
                )
            )
        rule_entry[sharing_type] = tiers[tier]
        rule_name = tier
        return ServiceRule("prescription_medicine[{}]".format(rule_name), rule_entry)

    def apply_cost_sharing_prescription(self, rx_name, rx_utilization_details, rx_price, generic_price=None):
        """
        Applies cost sharing to a given prescription price based on the type of medication.

        Args:
            rx_name (str): The name of the prescription.
            rx_utilization_details (dict): Type, frequency, and optional category /
                network / generic_substitute details of the prescription.
            rx_price (float): The price of the prescription before cost sharing.
            generic_price (float): Price of a cheaper generic equivalent, when the
                utilization profile lists one via `generic_substitute`.

        Returns:
            float: The price of the prescription after cost sharing.
        """
        tier = rx_utilization_details["type"]
        category = rx_utilization_details.get("category")
        network_coverage_level = rx_utilization_details.get("network", "in_network")

        rx_entry = self._prescription_entry(network_coverage_level)
        if rx_entry is None:
            print("No prescription benefit for {} at network level {}".format(rx_name, network_coverage_level))
            print("Member pays full price: {}".format(rx_price))
            return rx_price

        # "Member pays the difference" generic substitution: the plan shares
        # cost as if the generic had been dispensed, so the generic tier's
        # rule applies (a category override, if any, takes precedence). The
        # price difference between the dispensed drug and its generic is
        # uncovered: no deductible or OOP credit.
        #
        # Naming a generic_substitute on the medication is what opts it in, so
        # any non-generic tier qualifies (brand, specialty, ...). Substitution
        # only applies when the named substitute is actually cheaper, and it
        # needs a way to price the generic: a category override supplies that,
        # or else the tier table must include a generic tier. Without any of
        # those, the dispensed drug is priced at its own tier.
        override = (rx_entry.get("overrides") or {}).get(category) if category else None
        sharing_type = "copay" if "copay" in rx_entry else "coinsurance" if "coinsurance" in rx_entry else None
        can_price_generic = override is not None or (
            sharing_type is not None and "generic" in rx_entry.get(sharing_type, {})
        )
        difference = 0.0
        share_price = rx_price
        rule_tier = tier
        if (
            rx_entry.get("generic_substitution") == "member_pays_difference"
            and generic_price is not None
            and generic_price < rx_price
            and tier != "generic"
            and can_price_generic
        ):
            difference = rx_price - generic_price
            share_price = generic_price
            rule_tier = "generic"

        rule = self._build_prescription_rule(rx_entry, network_coverage_level, rule_tier, category)
        shared_cost = self._apply_rule(rule, share_price, network_coverage_level)
        return shared_cost + difference

    def _apply_rule(self, rule: ServiceRule, cost_before_deductible: float, network_coverage_level: str) -> float:
        """
        Applies a cost-sharing rule to a price, subtracting from the deductible
        and out-of-pocket max balances as needed. The member's cost is always
        capped at the remaining out-of-pocket maximum (unless the service is
        excluded from it).

        Args:
            rule: The cost-sharing rule to apply.
            cost_before_deductible: The price of the service before cost sharing.
            network_coverage_level: in_network or out_of_network.

        Returns:
            The cost of the service after cost sharing has been applied.
        """
        deductible, out_of_pocket_max = self._balances_for(network_coverage_level)
        cost_after_deductible = rule.cost_after_deductible(cost_before_deductible)

        # Once the out-of-pocket maximum is met, covered services cost nothing.
        if rule.counts_toward_oop_max and out_of_pocket_max.get_balance() <= 0:
            return 0.0

        if deductible.get_balance() <= 0 or not rule.deductible_applies:
            # Deductible met (or not applicable): member pays coinsurance/copay.
            member_cost = cost_after_deductible
            deductible_payment = 0.0
        elif deductible.get_balance() <= cost_before_deductible:
            # The deductible will be met by this service: pay the remaining
            # deductible, then cost sharing on the rest.
            if rule.sharing_type == "copay":
                # Pay the copay unless the remaining cost of the service is
                # less than the copay (e.g. after paying the last $90 of a
                # deductible towards a $100 service, you pay the last $10
                # instead of a $20 copay).
                remainder_cost = min(cost_after_deductible, cost_before_deductible - deductible.get_balance())
            else:  # coinsurance
                remainder_cost = (cost_before_deductible - deductible.get_balance()) * (rule.amount / 100)
            deductible_payment = deductible.get_balance()
            member_cost = deductible_payment + remainder_cost
        else:
            # Deductible not met by this service: member pays the full cost.
            deductible_payment = cost_before_deductible
            member_cost = cost_before_deductible

        if rule.counts_toward_oop_max:
            member_cost = min(member_cost, out_of_pocket_max.get_balance())
            out_of_pocket_max.subtract_balance(member_cost)
        deductible.subtract_balance(min(deductible_payment, member_cost))
        return member_cost


def create_healthcare_plans(plan_data, family_size):
    healthcare_plans = {}
    for plan_name, details in plan_data.items():
        # Get the HSA funding amount for the given family size
        if details.get("HSA_funding"):
            family_mapping = FAMILY_SIZE_MAP.get(family_size, FAMILY_SIZE_MAP[3])
            HSA_funding_amount = details["HSA_funding"][family_mapping]
        else:
            HSA_funding_amount = 0
        healthcare_plans[plan_name] = HealthcarePlan(
            name=plan_name,
            company=details["company"],
            description=details["description"],
            network_family=details.get("network_family", "N/A"),
            contributions=details["contributions"],
            HSA_funding=HSA_funding_amount,
            cost_sharing=details["cost_sharing"],
            out_of_network_coverage=details["out_of_network_coverage"],
            plan_deductibles=details["deductibles"],
            plan_out_of_pocket_max=details["out_of_pocket_max"],
            family_size=family_size,
        )

    return healthcare_plans


class HealthSim:
    def __init__(self, healthcare_plans, service_prices, utilization):
        self.service_prices = service_prices
        self.utilization = utilization
        self.family_size = len(self.utilization)
        self.healthcare_plans = create_healthcare_plans(healthcare_plans, self.family_size)


    def simulate(self):
        simulation_results = {}

        for plan_name, plan in self.healthcare_plans.items():
            cost_premium = plan.calculate_total_premium(self.family_size)
            cost_utilization = 0
            for member, member_utilization in self.utilization.items():
                # Reset the member balance for each deductible and out-of-pocket max,
                # and the occurrence counters, when we are processing a different
                # member's utilization.
                for deductible in plan.deductibles.values():
                    deductible.reset_member_balance()
                for out_of_pocket in plan.out_of_pocket_max.values():
                    out_of_pocket.reset_member_balance()
                plan.reset_member_usage()

                for coverage_level, utilization in (member_utilization.get('service_utilization') or {}).items():
                    if not utilization:
                        continue
                    for service, spec in utilization.items():
                        # Service entries may be a plain count or a mapping
                        # like {count: 2, admitted: true}.
                        if isinstance(spec, dict):
                            count = spec.get("count", 0)
                            options = spec
                        else:
                            count = spec
                            options = {}
                        for _ in range(count):
                            member_cost = plan.apply_cost_sharing_service(
                                network_coverage_level=coverage_level,
                                service_type=service,
                                service_price=self.service_prices.get(service, {}).get("cost", 0),
                                service_options=options,
                            )
                            cost_utilization += member_cost

                for rx_name, rx_utilization_details in (member_utilization.get('medications') or {}).items():
                    for _ in range(rx_utilization_details.get('frequency', 0)):
                        generic_price = None
                        substitute = rx_utilization_details.get('generic_substitute')
                        if substitute:
                            generic_price = (
                                self.service_prices.get('prescription_medicine', {})
                                .get(substitute, {})
                                .get('cost')
                            )
                        cost_medication = plan.apply_cost_sharing_prescription(
                            rx_name=rx_name,
                            rx_utilization_details=rx_utilization_details,
                            rx_price=self.service_prices.get('prescription_medicine', {}).get(rx_name, {}).get('cost', 0),
                            generic_price=generic_price,
                        )
                        cost_utilization += cost_medication

            simulation_results[plan_name] = {
                "cost_premium": cost_premium,
                "cost_utilization": cost_utilization,
            }

            simulation_results[plan_name]["cost_utilization_after_HSA"] = max(cost_utilization - plan.HSA_funding, 0)
            simulation_results[plan_name]["remaining_HSA_balance"] =  max(plan.HSA_funding - cost_utilization, 0)
            simulation_results[plan_name]["total_cost"] = (
                simulation_results[plan_name]["cost_premium"]
                + simulation_results[plan_name]["cost_utilization_after_HSA"]
            )

        return simulation_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcare_plans", "-hp", default=HEALTHCARE_PLANS_PATH, help="Path to healthcare plans YAML file")
    parser.add_argument("--service_prices", "-sp", default=SERVICE_PRICES_PATH, help="Path to service prices YAML file")
    parser.add_argument("--utilization", "-u", default=UTILIZATION_PATH, help="Path to utilization YAML file")
    args = parser.parse_args()

    healthcare_plans_dict = load_yaml_file(args.healthcare_plans)
    service_prices_dict = load_yaml_file(args.service_prices)
    utilization_dict = load_yaml_file(args.utilization)

    sim = HealthSim(healthcare_plans_dict, service_prices_dict, utilization_dict)
    results = sim.simulate()
    print("The results are in!")
    print(yaml.dump(results))
