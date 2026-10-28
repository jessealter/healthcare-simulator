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
    # the remaining $250 (coinsurance) = $75, but the out-of-pocket maximum
    # caps John's total year's cost at $2,000, so he pays only the last $50.
    # (The pre-refactor simulator let the member exceed the out-of-pocket
    # maximum here; its expected total of $2,025 encoded that bug.)
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
    for profile in [
        "profile_minimal_needs",
        "profile_diabetes",
        "profile_family_of_four",
        "profile_new_baby",
    ]:
        utilization = read_utilization(f"scenarios/{profile}.yml")
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
