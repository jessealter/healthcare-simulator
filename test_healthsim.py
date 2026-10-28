import copy
import glob

import pytest

from healthsim import (
    HealthSim,
    read_healthcare_plans,
    read_service_prices,
    read_utilization,
)

# Load the existing data from YAML files for reference in tests
service_prices = read_service_prices("scenarios/common_prices.yml")
healthcare_plans = read_healthcare_plans("scenarios/common_plans.yml")
utilization = read_utilization("scenarios/profile_minimal_needs.yml")


@pytest.fixture
def health_sim_instance(
    healthcare_plans=healthcare_plans,
    service_prices=service_prices,
    utilization=utilization,
):
    return HealthSim(healthcare_plans, service_prices, utilization)


def test_coherency():
    """
    Basic smoke test to ensure that the simulator can handle at least the most basic case.
    This uses hard-coded plan, pricing, and utilization data, and uses a single-person family
    with basic healthcare needs.
    """
    # Define healthcare plans for the simulation.
    # Maybe one is enough. Pretend the test universe has single payer healthcare?
    simple_plans = {
        "Simple Plan": {
            # 🎤 I'm just a kid and life is a nightmare
            "company": "QuackCare",
            "description": "A high-deductible plan without out-of-network coverage.",
            "network_family": "QC",
            "contributions": {
                "employee_only": 700,
                "employee_plus_one": 1400,
                "family": 2200,
            },
            "HSA_funding": {
                "employee_only": 500,
                "employee_plus_one": 750,
                "family": 1000,
            },
            "deductibles": {
                "in_network": {
                    "per_member": False,
                    "member": 2000,
                    "family": 4000,
                },
                "out_of_network": {},
            },
            "out_of_network_coverage": False,
            "out_of_pocket_max": {
                "in_network": {
                    "per_member": True,
                    "member": 2000,
                    "family": 4000,
                },
                "out_of_network": {},
            },
            "cost_sharing": {
                "in_network": {
                    "preventive_care": {"copay": 0},
                    "primary_care": {"coinsurance": 10},
                    "specialist_visit": {"coinsurance": 10},
                    "emergency_room": {"copay": 150},
                    "urgent_care": {"coinsurance": 10},
                    "prescription_medicine": {
                        "coinsurance": {
                            "generic": 10,
                            "brand_preferred": 10,
                            "brand_non-preferred": 10,
                        }
                    },
                    "hospital_stay": {"coinsurance": 10},
                },
                "out_of_network": {},
            },
        }
    }

    # Define a simple price list
    # Alas, would that healthcare pricing were so simple!
    simple_prices = {
        "primary_care": {"cost": 150},
        "specialist_visit": {"cost": 200},
        "emergency_room": {"cost": 500},
        "prescription_medicine": {
            "Medication_X": {"cost": 150},
            "Medication_Y": {"cost": 85},
            "Medication_Z": {"cost": 300},
        },
    }

    # Define a simple utilization profile
    simple_utilization = {
        "John": {
            "service_utilization": {
                "in_network": {
                    "primary_care": 1,
                },
                "out_of_network": {},
            },
            "medications": {
                "Medication_Z": {
                    "type": "generic",
                    "frequency": 7,
                }
            },
        },
    }

    # Manually calculate the service costs.
    # The office visit is processed while the deductible is unmet, so John
    # pays the full $150, which counts toward the $2,000 deductible.
    expected_primary_care_cost = (
        simple_prices["primary_care"]["cost"]
        * simple_utilization["John"]["service_utilization"]["in_network"][
            "primary_care"
        ]
    )
    print("expected_primary_care_cost: ", expected_primary_care_cost)

    # Add the cost of John's medications.
    # After the office visit, $1,850 of deductible remains. Six $300 fills go
    # entirely toward it, leaving $50 of deductible and $50 of out-of-pocket
    # maximum. The seventh fill would cost $50 (remaining deductible) + 10% of
    # the remaining $250 (coinsurance) = $75, but a member's costs never exceed
    # the out-of-pocket maximum, so John pays only the last $50 and his total
    # for the year is $2,000.
    expected_medication_cost = 6 * 300 + 50
    print("expected_medication_cost: ", expected_medication_cost)


    # Instantiate the HealthSim class with simple utilization
    simple_health_sim = HealthSim(simple_plans, simple_prices, simple_utilization)
    results = simple_health_sim.simulate()

    # The plan cost will be verified against one of the plan's total cost details
    plan_name = "Simple Plan"
    expected_premium = simple_plans[plan_name]["contributions"]["employee_only"]
    expected_utilization_cost = expected_primary_care_cost + expected_medication_cost
    # Assert costs are as expected for the chosen plan
    print(plan_name)
    print(results[plan_name])

    # fmt: off
    assert results[plan_name]["cost_premium"] == expected_premium, "incorrect premium cost" 
    assert results[plan_name]["cost_utilization"] == expected_utilization_cost, "incorrect utilization cost"
    assert results[plan_name]["cost_utilization_after_HSA"] == expected_utilization_cost - 500, "incorrect utilization cost after HSA applied"
    assert results[plan_name]["remaining_HSA_balance"] == 0, "incorrect remaining HSA balance"
    assert results[plan_name]["total_cost"] == expected_premium + expected_utilization_cost - 500, "incorrect total cost"
    # fmt: on


# ---------------------------------------------------------------------------
# Helpers for the feature tests below.
# ---------------------------------------------------------------------------

def make_plan(**overrides):
    """A minimal copay plan with a deductible, customizable per test."""
    plan = {
        "company": "QuackCare",
        "description": "Test plan",
        "network_family": "QC",
        "contributions": {
            "employee_only": 700,
            "employee_plus_one": 1400,
            "family": 2200,
        },
        "HSA_funding": None,
        "deductibles": {
            "in_network": {"per_member": False, "member": 2000, "family": 4000},
        },
        "out_of_network_coverage": False,
        "out_of_pocket_max": {
            "in_network": {"per_member": False, "member": 4000, "family": 8000},
        },
        "cost_sharing": {
            "in_network": {
                "preventive_care": {"copay": 0},
                "primary_care": {"copay": 20},
                "specialist_visit": {"copay": 30},
                "emergency_room": {"copay": 150, "waived_if_admitted": True},
                "hospital_stay": {"coinsurance": 10},
                "skilled_nursing_care": {"copay": 0, "limit": {"max": 2}},
                "durable_medical_equipment": {"copay": 100, "counts_toward_oop_max": False},
                "child_eyewear": {"copay": 0, "max_plan_paid": 150, "counts_toward_oop_max": False},
                "prescription_medicine": {
                    "copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45},
                },
            },
        },
    }
    plan.update(overrides)
    return {"Test Plan": plan}


def make_prices(**overrides):
    prices = {
        "primary_care": {"cost": 150},
        "specialist_visit": {"cost": 200},
        "emergency_room": {"cost": 1200},
        "hospital_stay": {"cost": 5000},
        "skilled_nursing_care": {"cost": 200},
        "durable_medical_equipment": {"cost": 500},
        "child_eyewear": {"cost": 300},
        "prescription_medicine": {
            "Medication_X": {"cost": 150},
            "Brand_AB": {"cost": 300},
            "Generic_AB": {"cost": 100},
            "GLP1_Drug": {"cost": 1000},
        },
    }
    prices.update(overrides)
    return prices


def simulate(plans, prices, utilization):
    return HealthSim(plans, prices, utilization).simulate()["Test Plan"]


def single_member(services=None, medications=None):
    return {
        "John": {
            "service_utilization": {"in_network": services or {}, "out_of_network": {}},
            "medications": medications or {},
        }
    }


def test_copay_bypasses_deductible_by_default():
    """Copays apply immediately; the deductible only gates coinsurance
    services (unless the plan says otherwise)."""
    result = simulate(make_plan(), make_prices(), single_member(services={"primary_care": 3}))
    assert result["cost_utilization"] == 3 * 20


def test_copay_can_apply_after_deductible_when_plan_says_so():
    """HDHP-style ER copay: full price until the deductible is met."""
    plans = make_plan()
    plans["Test Plan"]["cost_sharing"]["in_network"]["emergency_room"] = {
        "copay": 150,
        "deductible_applies": True,
        "waived_if_admitted": True,
    }
    # Three ER visits at $1,200 each: $2,000 deductible + $150 copay + ... the
    # first visit eats $1,200 of deductible (member pays it all), the second
    # meets the remaining $800 then costs the $150 copay, the third is $150.
    result = simulate(plans, make_prices(), single_member(services={"emergency_room": 3}))
    expected = 1200 + (800 + 150) + 150
    assert result["cost_utilization"] == expected


def test_er_copay_waived_when_admitted():
    prices = make_prices()
    plans = make_plan()
    # Not admitted: plain $150 copay.
    result = simulate(plans, prices, single_member(services={"emergency_room": 1}))
    assert result["cost_utilization"] == 150
    # Admitted: ER copay waived; the admission is billed as a hospital stay.
    result = simulate(
        plans,
        prices,
        single_member(services={"emergency_room": {"count": 1, "admitted": True},
                                "hospital_stay": 1}),
    )
    # ER line: $0. Hospital stay: $5,000 price against a $2,000 deductible ->
    # $2,000 + 10% of the remaining $3,000 = $2,300.
    assert result["cost_utilization"] == 0 + (2000 + 0.10 * 3000)


def test_structured_entries_match_plain_counts():
    prices = make_prices()
    utilization = single_member(services={"primary_care": {"count": 2, "admitted": False}})
    assert (
        simulate(make_plan(), prices, utilization)["cost_utilization"]
        == simulate(make_plan(), prices, single_member(services={"primary_care": 2}))["cost_utilization"]
    )


def test_service_occurrence_limit():
    """Skilled nursing covered for 2 days (at $0); day 3+ is full price and
    credits nothing."""
    result = simulate(
        make_plan(), make_prices(), single_member(services={"skilled_nursing_care": 3})
    )
    assert result["cost_utilization"] == 0 + 0 + 200


def test_oop_excluded_service_keeps_charging():
    """Services excluded from the OOP max keep charging after it is met and
    never reduce it."""
    plans = make_plan()
    plans["Test Plan"]["out_of_pocket_max"]["in_network"] = {
        "per_member": False, "member": 300, "family": 300,
    }
    # $500 DME at $100 copay: copay applies but never touches the $300 OOP
    # max; then a $5,000 hospital stay costs the remaining $300 and stops.
    result = simulate(
        plans,
        make_prices(),
        single_member(services={"durable_medical_equipment": 1, "hospital_stay": 2}),
    )
    # DME: $100 (no OOP credit). Stay 1: 10% of $5,000 = $500 -> capped at
    # the $300 OOP max. Stay 2: OOP max met -> $0. Total $400.
    assert result["cost_utilization"] == 100 + 300 + 0


def test_allowance_benefit():
    """Plan pays up to $150 for children's eyewear; member pays the excess."""
    result = simulate(make_plan(), make_prices(), single_member(services={"child_eyewear": 1}))
    assert result["cost_utilization"] == 150
    # Cheap frames need no contribution.
    prices = make_prices()
    prices["child_eyewear"] = {"cost": 100}
    result = simulate(make_plan(), prices, single_member(services={"child_eyewear": 1}))
    assert result["cost_utilization"] == 0


def test_rx_category_override_bypasses_deductible():
    """GLP-1 style override: flat copay that bypasses the deductible."""
    plans = make_plan()
    plans["Test Plan"]["cost_sharing"]["in_network"]["prescription_medicine"] = {
        "coinsurance": {"generic": 10, "brand_preferred": 10, "brand_non-preferred": 10},
        "overrides": {
            "glp1_weight_loss": {"copay": 150, "deductible_applies": False},
        },
    }
    utilization = single_member(
        medications={"GLP1_Drug": {"type": "brand_preferred", "frequency": 1, "category": "glp1_weight_loss"}}
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == 150


def test_rx_generic_substitution_member_pays_difference():
    """Brand dispensed despite a cheaper generic: plan shares cost as if the
    generic were dispensed; the price difference is uncovered."""
    plans = make_plan()
    plans["Test Plan"]["cost_sharing"]["in_network"]["prescription_medicine"] = {
        "coinsurance": {"generic": 10, "brand_preferred": 10, "brand_non-preferred": 10},
        "generic_substitution": "member_pays_difference",
    }
    utilization = single_member(
        medications={"Brand_AB": {"type": "brand_preferred", "frequency": 1, "generic_substitute": "Generic_AB"}}
    )
    result = simulate(plans, make_prices(), utilization)
    # Deductible unmet: generic $100 goes toward it; the $200 difference is
    # uncovered. Total: $100 + $200 = $300.
    assert result["cost_utilization"] == 300


def test_scenario_plans_simulate_all_profiles():
    """Schema validation: every demo plan in scenarios/common_plans.yml
    parses and simulates against every shipped utilization profile without
    raising, and produces numeric totals."""
    plans = read_healthcare_plans("scenarios/common_plans.yml")
    prices = read_service_prices("scenarios/common_prices.yml")
    profiles = sorted(glob.glob("scenarios/profile_*.yml"))
    assert profiles, "no utilization profiles found under scenarios/"
    for profile in profiles:
        utilization = read_utilization(profile)
        results = HealthSim(plans, prices, utilization).simulate()
        assert set(results) == set(plans)
        for plan_name, result in results.items():
            assert isinstance(result["cost_utilization"], float)
            assert result["cost_utilization"] >= 0
            assert result["total_cost"] >= result["cost_premium"]


# ---------------------------------------------------------------------------
# Prescription rule resolution: plan-wide Rx settings must reach every rule
# built for a fill (tier, category override, generic substitution).
# ---------------------------------------------------------------------------

def rx_plan(rx_entry, deductible=2000, oop=4000):
    """A plan whose prescription benefit is `rx_entry`, with single-pot
    deductible and out-of-pocket max sized by the caller."""
    plans = make_plan()
    plan = plans["Test Plan"]
    plan["deductibles"]["in_network"] = {"per_member": False, "member": deductible, "family": deductible}
    plan["out_of_pocket_max"]["in_network"] = {"per_member": False, "member": oop, "family": oop}
    plan["cost_sharing"]["in_network"]["prescription_medicine"] = rx_entry
    return plans


def test_rx_plan_wide_oop_exclusion_keeps_charging():
    """A prescription benefit excluded from the OOP max keeps charging its
    copay after the OOP max is met and never reduces it."""
    plans = rx_plan(
        {
            "copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45},
            "counts_toward_oop_max": False,
        },
        deductible=0,
        oop=50,
    )
    utilization = single_member(
        services={"hospital_stay": 1},  # 10% of $5,000 = $500, capped at the $50 OOP max
        medications={"Medication_X": {"type": "generic", "frequency": 2}},
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == 50 + 2 * 10


def test_rx_override_inherits_plan_wide_deductible_default():
    """An override that sets only coinsurance still inherits the prescription
    entry's deductible_applies: false."""
    plans = rx_plan(
        {
            "coinsurance": {"generic": 10, "brand_preferred": 30, "brand_non-preferred": 30},
            "deductible_applies": False,
            "overrides": {"special": {"coinsurance": 20}},
        }
    )
    utilization = single_member(
        medications={"Medication_X": {"type": "brand_preferred", "frequency": 1, "category": "special"}}
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == pytest.approx(0.20 * 150)  # not the full $150


def test_rx_override_fields_take_precedence_over_plan_wide_defaults():
    """An override's own deductible_applies beats the plan-wide default."""
    plans = rx_plan(
        {
            "coinsurance": {"generic": 10, "brand_preferred": 30, "brand_non-preferred": 30},
            "deductible_applies": False,
            "overrides": {"special": {"coinsurance": 20, "deductible_applies": True}},
        }
    )
    utilization = single_member(
        medications={"Medication_X": {"type": "brand_preferred", "frequency": 1, "category": "special"}}
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == 150  # deductible ($2,000) unmet, so full price


def test_rx_generic_substitution_uses_generic_tier_rule():
    """With substitution, the plan shares cost as if the generic were
    dispensed, at the generic tier's rate, and only that copay credits the
    out-of-pocket max; the brand/generic difference credits nothing."""
    plans = rx_plan(
        {
            "copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45},
            "generic_substitution": "member_pays_difference",
        },
        deductible=0,
        oop=1000,
    )
    utilization = single_member(
        medications={"Brand_AB": {"type": "brand_preferred", "frequency": 1, "generic_substitute": "Generic_AB"}}
    )
    sim = HealthSim(plans, make_prices(), utilization)
    result = sim.simulate()["Test Plan"]
    assert result["cost_utilization"] == 10 + 200  # generic copay + ($300 - $100)
    assert sim.healthcare_plans["Test Plan"].out_of_pocket_max["in_network"].get_balance() == 1000 - 10


def test_rx_generic_substitution_keeps_category_override():
    """A category override still wins when substitution applies."""
    plans = rx_plan(
        {
            "copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45},
            "generic_substitution": "member_pays_difference",
            "overrides": {"flat": {"copay": 5}},
        },
        deductible=0,
    )
    utilization = single_member(
        medications={
            "Brand_AB": {
                "type": "brand_preferred",
                "frequency": 1,
                "category": "flat",
                "generic_substitute": "Generic_AB",
            }
        }
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == 5 + 200


# ---------------------------------------------------------------------------
# Prescription tier validation, generic substitution for any non-generic tier,
# and occurrence limits shared across networks.
# ---------------------------------------------------------------------------

def test_rx_category_override_does_not_require_a_matching_tier():
    """An override supplies the whole rule, so the drug's tier need not exist
    in the plan's tier table."""
    plans = rx_plan(
        {
            "copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45},
            "overrides": {"special": {"copay": 40}},
        },
        deductible=0,
    )
    utilization = single_member(
        medications={"Medication_X": {"type": "speciality", "frequency": 1, "category": "special"}}
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == 40


def test_rx_unknown_tier_without_override_raises():
    """The tier is validated whenever no override supplies the rule."""
    plans = rx_plan({"copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45}})
    utilization = single_member(
        medications={"Medication_X": {"type": "speciality", "frequency": 1}}
    )
    with pytest.raises(KeyError):
        simulate(plans, make_prices(), utilization)


def test_rx_generic_substitution_applies_to_specialty_tier():
    """Naming a generic_substitute is the opt-in; the dispensed drug's tier
    name does not have to start with 'brand'."""
    plans = rx_plan(
        {
            "coinsurance": {"generic": 10, "brand_preferred": 10, "brand_non-preferred": 10, "speciality": 10},
            "generic_substitution": "member_pays_difference",
        },
        deductible=0,
    )
    utilization = single_member(
        medications={"Brand_AB": {"type": "speciality", "frequency": 1, "generic_substitute": "Generic_AB"}}
    )
    result = simulate(plans, make_prices(), utilization)
    # 10% of the $100 generic plus the $200 price difference, not 10% of $300.
    assert result["cost_utilization"] == pytest.approx(10 + 200)


def test_rx_generic_substitution_ignored_for_drugs_already_generic():
    """A drug already in the generic tier has nothing to substitute."""
    plans = rx_plan(
        {
            "coinsurance": {"generic": 10, "brand_preferred": 10, "brand_non-preferred": 10},
            "generic_substitution": "member_pays_difference",
        },
        deductible=0,
    )
    utilization = single_member(
        medications={"Medication_X": {"type": "generic", "frequency": 1, "generic_substitute": "Generic_AB"}}
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == pytest.approx(0.10 * 150)


def snf_plan(out_of_network_covered):
    """make_plan() plus a two-day skilled nursing limit at both network levels."""
    plans = make_plan()
    plan = plans["Test Plan"]
    plan["out_of_network_coverage"] = out_of_network_covered
    plan["cost_sharing"]["out_of_network"] = {
        "skilled_nursing_care": {"copay": 0, "limit": {"max": 2}},
    }
    return plans


def test_occurrence_limit_is_shared_across_networks():
    """limit.max is an annual per-member cap: switching networks must not
    refill it."""
    utilization = {
        "John": {
            "service_utilization": {
                "in_network": {"skilled_nursing_care": 2},
                "out_of_network": {"skilled_nursing_care": 1},
            },
            "medications": {},
        }
    }
    result = simulate(snf_plan(True), make_prices(), utilization)
    assert result["cost_utilization"] == 200  # the third day is past the cap


def test_uncovered_days_do_not_use_up_the_occurrence_limit():
    """A day the plan does not cover at all (no out-of-network benefit) is
    billed in full and must not burn the in-network allowance, whichever
    order the utilization is listed in."""
    utilization = {
        "John": {
            "service_utilization": {
                "out_of_network": {"skilled_nursing_care": 1},
                "in_network": {"skilled_nursing_care": 2},
            },
            "medications": {},
        }
    }
    result = simulate(snf_plan(False), make_prices(), utilization)
    assert result["cost_utilization"] == 200  # only the uncovered out-of-network day


def test_occurrence_limit_resets_for_each_member():
    days = {
        "service_utilization": {"in_network": {"skilled_nursing_care": 2}, "out_of_network": {}},
        "medications": {},
    }
    result = simulate(snf_plan(True), make_prices(), {"John": days, "Michelle": days})
    assert result["cost_utilization"] == 0  # two covered days each; the cap is per member


def test_occurrence_limit_resolves_consistently_when_networks_differ():
    """A service with different limits per network resolves to one cap
    (in-network wins), so the total does not depend on processing order."""
    plans = make_plan()
    plan = plans["Test Plan"]
    plan["out_of_network_coverage"] = True
    # make_plan already gives in-network skilled_nursing_care limit=2; give the
    # out-of-network entry a different limit.
    plan["cost_sharing"]["out_of_network"] = {
        "skilled_nursing_care": {"copay": 0, "limit": {"max": 10}},
    }

    def total(order):
        utilization = {"John": {"service_utilization": order, "medications": {}}}
        return simulate(plans, make_prices(), utilization)["cost_utilization"]

    oon_first = total({"out_of_network": {"skilled_nursing_care": 5}, "in_network": {"skilled_nursing_care": 5}})
    in_first = total({"in_network": {"skilled_nursing_care": 5}, "out_of_network": {"skilled_nursing_care": 5}})
    assert oon_first == in_first
    # The in-network cap (2) governs: 2 covered days at $0, 8 at $200 each.
    assert in_first == 8 * 200


def test_occurrence_limit_is_one_shared_cap_when_one_network_has_no_limit():
    """A service capped in one network but not the other still shares a single
    annual cap, resolved deterministically regardless of processing order."""
    plans = make_plan()
    plan = plans["Test Plan"]
    plan["out_of_network_coverage"] = True
    plan["cost_sharing"]["out_of_network"] = {"skilled_nursing_care": {"copay": 0}}  # no limit

    def total(order):
        utilization = {"John": {"service_utilization": order, "medications": {}}}
        return simulate(plans, make_prices(), utilization)["cost_utilization"]

    oon_first = total({"out_of_network": {"skilled_nursing_care": 3}, "in_network": {"skilled_nursing_care": 3}})
    in_first = total({"in_network": {"skilled_nursing_care": 3}, "out_of_network": {"skilled_nursing_care": 3}})
    assert oon_first == in_first == 4 * 200  # 2 covered, 4 at full $200


def test_waived_copay_beats_occurrence_limit():
    """An admitted visit is waived even when past the occurrence limit."""
    plans = make_plan()
    plan = plans["Test Plan"]
    plan["cost_sharing"]["in_network"]["emergency_room"] = {
        "copay": 150, "waived_if_admitted": True, "limit": {"max": 2},
    }
    plan_obj = HealthSim(plans, make_prices(), single_member()).healthcare_plans["Test Plan"]
    first = plan_obj.apply_cost_sharing_service("in_network", "emergency_room", 1200, {})
    second = plan_obj.apply_cost_sharing_service("in_network", "emergency_room", 1200, {})
    third = plan_obj.apply_cost_sharing_service("in_network", "emergency_room", 1200, {"admitted": True})
    assert (first, second, third) == (150, 150, 0)


# ---------------------------------------------------------------------------
# Shipped scenario: generic substitution end to end.
# ---------------------------------------------------------------------------

def test_brand_over_generic_profile_penalises_only_plans_with_the_rule():
    plans = read_healthcare_plans("scenarios/common_plans.yml")
    prices = read_service_prices("scenarios/common_prices.yml")
    utilization = read_utilization("scenarios/profile_brand_over_generic.yml")
    results = HealthSim(plans, prices, utilization).simulate()

    # PlanOne has a member-pays-the-difference rule. Under its $2,000
    # deductible, the $195 office visit and each of the twelve fills priced at
    # the $90 generic are paid in full (total $1,275, well under the $3,000
    # out-of-pocket max). Each fill also carries the uncovered gap between the
    # $300 brand price and the $90 generic.
    assert results["PlanOne"]["cost_utilization"] == pytest.approx(195 + 12 * 90 + 12 * (300 - 90))

    # The other demo plans have no such rule, so they ignore the named
    # substitute: a $20 office copay plus a $25 brand copay per fill.
    for plan_name in ("PlanTwo", "PlanA", "Plan B"):
        assert results[plan_name]["cost_utilization"] == pytest.approx(20 + 12 * 25)

    # The field is what drives the difference. Without it, PlanOne prices the
    # fills as ordinary brand coinsurance: the visit leaves $1,805 of deductible,
    # six $300 fills use $1,800 of it, the seventh pays the last $5 plus 10% of
    # the remaining $295, and the last five pay 10% of $300.
    without_substitute = copy.deepcopy(utilization)
    del without_substitute["Jordan"]["medications"]["Popular_Brand_Drug"]["generic_substitute"]
    results = HealthSim(plans, prices, without_substitute).simulate()
    assert results["PlanOne"]["cost_utilization"] == pytest.approx(
        195 + 6 * 300 + (5 + 0.10 * 295) + 5 * 0.10 * 300
    )


def test_rx_generic_substitution_skips_when_no_generic_tier():
    """A plan without a generic tier cannot price the substitution, so the
    dispensed drug is priced at its own tier instead of crashing."""
    plans = rx_plan(
        {
            "copay": {"brand_preferred": 25, "brand_non-preferred": 45},
            "generic_substitution": "member_pays_difference",
        },
        deductible=0,
    )
    utilization = single_member(
        medications={"Brand_AB": {"type": "brand_preferred", "frequency": 1, "generic_substitute": "Generic_AB"}}
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == 25


def test_rx_override_does_not_require_a_tier_table():
    """An override supplies the whole rule, so a prescription entry that has
    only overrides and no copay/coinsurance tier table still works."""
    plans = rx_plan({"overrides": {"special": {"copay": 40}}})
    utilization = single_member(
        medications={"Medication_X": {"type": "speciality", "frequency": 1, "category": "special"}}
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == 40


def test_rx_generic_substitution_requires_a_cheaper_generic():
    """Naming a generic_substitute only matters when the substitute is
    actually cheaper. An equal-priced one is not a cheaper equivalent, so the
    dispensed drug is priced at its own tier."""
    plans = rx_plan(
        {
            "copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45},
            "generic_substitution": "member_pays_difference",
        },
        deductible=0,
    )
    utilization = single_member(
        medications={"Brand_AB": {"type": "brand_preferred", "frequency": 1, "generic_substitute": "Generic_AB"}}
    )
    prices = make_prices()
    prices["prescription_medicine"]["Generic_AB"] = {"cost": 300}  # same price as the brand
    result = simulate(plans, prices, utilization)
    assert result["cost_utilization"] == 25  # the brand tier, not the $10 generic copay


def test_rx_out_of_network_requires_out_of_network_coverage():
    """A plan with out_of_network_coverage: false never applies an
    out-of-network pharmacy benefit, even if one is declared: the fill is
    full price and credits no accumulator."""
    plans = rx_plan(
        {"copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45}},
        deductible=2000, oop=1000,
    )
    plan = plans["Test Plan"]
    # make_plan leaves out_of_network_coverage False; declare an
    # out-of-network pharmacy table to prove it is ignored.
    plan["cost_sharing"]["out_of_network"] = {
        "prescription_medicine": {"copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45}},
    }
    utilization = single_member(
        medications={"Brand_AB": {"type": "brand_preferred", "frequency": 1, "network": "out_of_network"}}
    )
    sim = HealthSim(plans, make_prices(), utilization)
    result = sim.simulate()["Test Plan"]
    assert result["cost_utilization"] == 300  # full price, not the $25 copay
    plan_obj = sim.healthcare_plans["Test Plan"]
    assert plan_obj.deductibles["in_network"].get_balance() == 2000  # no deductible credit
    assert plan_obj.out_of_pocket_max["in_network"].get_balance() == 1000  # no OOP credit


def test_rx_out_of_network_benefit_applies_oon_rates():
    """With out-of-network coverage on, an out-of-network fill is priced at
    the out-of-network tier, distinct from the in-network tier."""
    plans = rx_plan(
        {"copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45}},
        deductible=0,
    )
    plan = plans["Test Plan"]
    plan["out_of_network_coverage"] = True
    plan["cost_sharing"]["out_of_network"] = {
        "prescription_medicine": {"copay": {"generic": 15, "brand_preferred": 40, "brand_non-preferred": 60}},
    }
    utilization = single_member(
        medications={"Brand_AB": {"type": "brand_preferred", "frequency": 1, "network": "out_of_network"}}
    )
    result = simulate(plans, make_prices(), utilization)
    assert result["cost_utilization"] == 40  # the $40 OON copay, not $25


def test_rx_out_of_network_no_benefit_charges_full_price():
    """A plan with out-of-network coverage but no out-of-network pharmacy
    entry charges full price for an out-of-network fill, crediting neither
    the deductible nor the OOP max."""
    plans = rx_plan(
        {"copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45}},
        deductible=2000, oop=1000,
    )
    plan = plans["Test Plan"]
    plan["out_of_network_coverage"] = True  # covered, but no OON pharmacy benefit
    utilization = single_member(
        medications={"Brand_AB": {"type": "brand_preferred", "frequency": 1, "network": "out_of_network"}}
    )
    sim = HealthSim(plans, make_prices(), utilization)
    result = sim.simulate()["Test Plan"]
    assert result["cost_utilization"] == 300
    plan_obj = sim.healthcare_plans["Test Plan"]
    assert plan_obj.deductibles["in_network"].get_balance() == 2000
    assert plan_obj.out_of_pocket_max["in_network"].get_balance() == 1000


def test_rx_out_of_network_null_benefit_charges_full_price():
    """An explicitly null out-of-network pharmacy entry behaves like an
    omitted one: the fill is full price with no accumulator credit."""
    plans = rx_plan(
        {"copay": {"generic": 10, "brand_preferred": 25, "brand_non-preferred": 45}},
        deductible=2000, oop=1000,
    )
    plan = plans["Test Plan"]
    plan["out_of_network_coverage"] = True
    plan["cost_sharing"]["out_of_network"] = {"prescription_medicine": None}
    utilization = single_member(
        medications={"Brand_AB": {"type": "brand_preferred", "frequency": 1, "network": "out_of_network"}}
    )
    sim = HealthSim(plans, make_prices(), utilization)
    result = sim.simulate()["Test Plan"]
    assert result["cost_utilization"] == 300
    plan_obj = sim.healthcare_plans["Test Plan"]
    assert plan_obj.deductibles["in_network"].get_balance() == 2000
    assert plan_obj.out_of_pocket_max["in_network"].get_balance() == 1000
