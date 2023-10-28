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
    # In this test, the medications is enough to meet the deductible, but not the out-of-pocket max.
    # So the office visit is effectively paid at 10%.
    expected_primary_care_cost = 0.1 * (
        simple_prices["primary_care"]["cost"]
        * simple_utilization["John"]["service_utilization"]["in_network"][
            "primary_care"
        ]
    )

    print("expected_primary_care_cost: ", expected_primary_care_cost)

    # Add the cost of John's medications
    expected_medication_cost = (
        6 * 300 + (2000 - 6 * 300) + 0.1 * (300 - (2000 - 6 * 300))
    )
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
