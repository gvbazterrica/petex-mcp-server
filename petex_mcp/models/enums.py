"""Enumeration types for the PETEX MCP Server.

Based on PROSPER, MBAL, and GAP technical documentation.
Covers all major options available in the PETEX IPM suite.
"""

from enum import Enum


# =============================================================================
# PROSPER Enumerations
# =============================================================================


class WellType(str, Enum):
    PRODUCER = "producer"
    INJECTOR = "injector"
    WATER_INJECTOR = "water_injector"
    CBM_PRODUCER = "cbm_producer"
    CO2_INJECTOR = "co2_injector"


class FluidType(str, Enum):
    OIL = "oil"  # Oil and Water
    GAS = "gas"  # Dry and Wet Gas
    CONDENSATE = "condensate"  # Retrograde Condensate
    WATER = "water"


class PVTMethod(str, Enum):
    BLACK_OIL = "black_oil"
    EQUATION_OF_STATE = "equation_of_state"
    NIST_REFERENCE = "nist_reference"


class WellTrajectory(str, Enum):
    VERTICAL = "vertical"
    DEVIATED = "deviated"
    HORIZONTAL = "horizontal"
    MULTILATERAL = "multilateral"


class FlowType(str, Enum):
    TUBING = "tubing"
    ANNULAR = "annular"
    TUBING_AND_ANNULAR = "tubing_and_annular"


class PredictionType(str, Enum):
    PRESSURE_ONLY = "pressure_only"
    PRESSURE_AND_TEMPERATURE_ONLAND = "pressure_and_temperature_onland"
    PRESSURE_AND_TEMPERATURE_OFFSHORE = "pressure_and_temperature_offshore"
    PRESSURE_AND_TEMPERATURE_SURFACE_GRADIENT = "pressure_and_temperature_surface_gradient"


class TemperatureModel(str, Enum):
    ROUGH_APPROXIMATION = "rough_approximation"
    ENTHALPY_BALANCE = "enthalpy_balance"
    IMPROVED_APPROXIMATION = "improved_approximation"


class SeparatorType(str, Enum):
    SINGLE_STAGE = "single_stage"
    TWO_STAGE = "two_stage"


class IPRModel(str, Enum):
    PI_ENTRY = "PI_Entry"
    VOGEL = "Vogel"
    COMPOSITE = "Composite"
    DARCY = "Darcy"
    JONES = "Jones"
    FETKOVITCH = "Fetkovitch"
    MULTI_RATE_FETKOVITCH = "Multi_Rate_Fetkovitch"
    MULTI_RATE_JONES = "Multi_Rate_Jones"
    TRANSIENT = "Transient"
    HYDRAULICALLY_FRACTURED = "Hydraulically_Fractured"
    HORIZONTAL_NO_FLOW = "Horizontal_No_Flow"
    HORIZONTAL_CONSTANT_PRESSURE = "Horizontal_Constant_Pressure"
    HORIZONTAL_DP_FRICTION = "Horizontal_dP_Friction"
    HORIZONTAL_TRANSVERSE_FRACTURES = "Horizontal_Transverse_Fractures"
    MULTI_LAYER = "Multi_Layer"
    MULTI_LAYER_DP = "Multi_Layer_dP"
    MULTI_LATERAL = "Multi_Lateral"
    EXTERNAL_ENTRY = "External_Entry"
    DUAL_POROSITY = "Dual_Porosity"
    SKINAIDE = "SkinAide"
    SPOT = "SPOT"
    THERMALLY_INDUCED_FRACTURE = "Thermally_Induced_Fracture"
    # Gas-specific
    BACK_PRESSURE = "Back_Pressure"
    C_AND_N = "C_and_n"
    MULTI_RATE_C_AND_N = "Multi_Rate_C_and_n"
    FORCHHEIMER = "Forchheimer"
    FORCHHEIMER_PSEUDO_PRESSURE = "Forchheimer_Pseudo_Pressure"
    MULTI_RATE_FORCHHEIMER_PSEUDO = "Multi_Rate_Forchheimer_Pseudo"
    PETROLEUM_EXPERTS_GAS = "Petroleum_Experts_Gas"
    MODIFIED_ISOCHRONAL = "Modified_Isochronal"
    CBM_PRODUCER = "CBM_Producer"
    # Legacy aliases
    HORIZONTAL_PI_JOSHI = "Horizontal_PI_Joshi"
    HORIZONTAL_PI_BABU_ODEH = "Horizontal_PI_Babu_Odeh"
    HORIZONTAL_PI_KUCHUK = "Horizontal_PI_Kuchuk"


class SkinModel(str, Enum):
    ENTER_BY_HAND = "Enter_By_Hand"
    LOCKE = "Locke"
    MACLEOD = "MacLeod"
    KARAKAS_TARIQ = "Karakas_Tariq"


class DeviationSkinModel(str, Enum):
    NONE = "None"
    CINCO_MARTING_BRONZ = "Cinco_Marting_Bronz"
    CINCO_2_MARTING_BRONZ = "Cinco_2_Marting_Bronz"
    WONG_CLIFFORD = "Wong_Clifford"


class SandControlType(str, Enum):
    NONE = "none"
    GRAVEL_PACK = "gravel_pack"
    PRE_PACKED_SCREEN = "pre_packed_screen"
    WIRE_WRAPPED_SCREEN = "wire_wrapped_screen"
    SLOTTED_LINER = "slotted_liner"


class VLPCorrelation(str, Enum):
    HAGEDORN_BROWN = "Hagedorn_Brown"
    BEGGS_BRILL = "Beggs_Brill"
    DUNS_ROS = "Duns_Ros"
    DUNS_ROS_ORIGINAL = "Duns_Ros_Original"
    FANCHER_BROWN = "Fancher_Brown"
    ORKISZEWSKI = "Orkiszewski"
    PETROLEUM_EXPERTS = "Petroleum_Experts"
    PETROLEUM_EXPERTS_2 = "Petroleum_Experts_2"
    PETROLEUM_EXPERTS_3 = "Petroleum_Experts_3"
    PETROLEUM_EXPERTS_4 = "Petroleum_Experts_4"
    PETROLEUM_EXPERTS_5 = "Petroleum_Experts_5"
    PETROLEUM_EXPERTS_5_EXTENDED = "Petroleum_Experts_5_Extended"
    PETROLEUM_EXPERTS_6 = "Petroleum_Experts_6"
    GRAY = "Gray"
    HYDRO_3P = "Hydro_3P"
    HYDRO_2P = "Hydro_2P"
    OLGAS_2P = "OLGAS_2P"
    OLGAS_3P = "OLGAS_3P"
    LEDAFLOW = "LedaFlow"
    ANSARI = "Ansari"
    GOVIER_AZIZ = "Govier_Aziz"
    MUKERJEE_BRILL = "Mukerjee_Brill"
    GRE_MODIFIED = "GRE_Modified"


class PipelineCorrelation(str, Enum):
    FANCHER_BROWN = "Fancher_Brown"
    MUKERJEE_BRILL = "Mukerjee_Brill"
    BEGGS_BRILL = "Beggs_Brill"
    BEGGS_BRILL_GAS_HEAD = "Beggs_Brill_Gas_Head"
    DUKLER_FLANIGAN = "Dukler_Flanigan"
    DUKLER_EATON_FLANIGAN = "Dukler_Eaton_Flanigan"
    GRE_MODIFIED = "GRE_Modified"
    PETROLEUM_EXPERTS_4 = "Petroleum_Experts_4"
    PETROLEUM_EXPERTS_5 = "Petroleum_Experts_5"
    HYDRO_3P = "Hydro_3P"
    OLGAS_2P = "OLGAS_2P"
    OLGAS_3P = "OLGAS_3P"


class CompletionType(str, Enum):
    OPEN_HOLE = "open_hole"
    CASED_PERFORATED = "cased_perforated"
    GRAVEL_PACK = "gravel_pack"
    FRAC_PACK = "frac_pack"
    OPEN_HOLE_GRAVEL_PACK = "open_hole_gravel_pack"
    SLOTTED_LINER = "slotted_liner"
    PRE_PACKED_SCREEN = "pre_packed_screen"
    WIRE_WRAPPED_SCREEN = "wire_wrapped_screen"


class LiftMethod(str, Enum):
    NONE = "none"
    GAS_LIFT_CONTINUOUS = "gas_lift_continuous"
    GAS_LIFT_INTERMITTENT = "gas_lift_intermittent"
    ESP = "ESP"
    HSP = "HSP"  # Hydraulic Submersible Pump
    PCP = "PCP"  # Progressive Cavity Pump
    COILED_TUBING_GAS_LIFT = "coiled_tubing_gas_lift"
    DILUENT_INJECTION = "diluent_injection"
    JET_PUMP = "jet_pump"
    MULTIPHASE_PUMP = "multiphase_pump"
    ROD_PUMP = "rod_pump"
    FOAM_LIFT = "foam_lift"
    PLUNGER_LIFT = "plunger_lift"


class GasLiftType(str, Enum):
    NO_FRICTION_ANNULUS = "no_friction_loss_in_annulus"
    FRICTION_ANNULUS = "friction_loss_in_annulus"
    SAFETY_EQUIPMENT = "safety_equipment"


class GasLiftMethod(str, Enum):
    FIXED_DEPTH = "fixed_depth_of_injection"
    OPTIMUM_DEPTH = "optimum_depth_of_injection"
    VALVE_DEPTHS_SPECIFIED = "valve_depths_specified"
    MULTIPOINT = "multipoint"


class ESPType(str, Enum):
    MODEL_OIL_ONLY = "model_produced_oil_only"
    MODEL_OIL_AND_GAS_ANNULUS = "model_produced_oil_and_gas_in_annulus"


class ChokeModel(str, Enum):
    PETROLEUM_EXPERTS = "Petroleum_Experts"
    HYDRO_SHORT = "Hydro_Short"
    HYDRO_LONG = "Hydro_Long"
    ELF = "ELF"
    VENTURI = "Venturi"
    MODIFIED_SACHDEVA = "Modified_Sachdeva"


class PbCorrelation(str, Enum):
    GLASO = "Glaso"
    STANDING = "Standing"
    LASATER = "Lasater"
    PETROSKY = "Petrosky"
    VASQUEZ_BEGGS = "Vasquez_Beggs"
    AL_MARHOUN = "Al_Marhoun"
    DE_GHETTO = "De_Ghetto"


class ViscosityCorrelation(str, Enum):
    BEAL = "Beal"
    BEGGS = "Beggs"
    PETROSKY = "Petrosky"
    EGBOGAH = "Egbogah"
    BERGMAN_SUTTON = "Bergman_Sutton"
    DE_GHETTO = "De_Ghetto"


class GasViscosityCorrelation(str, Enum):
    LEE = "Lee"
    CARR = "Carr"


class LiftCurveFormat(str, Enum):
    PETEX_GAP_MBAL = "Petroleum_Experts_GAP_MBAL"
    ECLIPSE = "Eclipse"
    INTERSECT = "Intersect"
    VIP = "VIP"
    CMG_IMEX_GEM = "CMG_IMEX_GEM"
    COMP4 = "COMP4"
    PEGASUS = "PEGASUS"
    POWERS = "POWERS"


class GasLiftDesignRate(str, Enum):
    ENTERED_BY_USER = "entered_by_user"
    CALCULATED_MAX_PRODUCTION = "calculated_max_production"
    CALCULATED_MAX_REVENUE = "calculated_max_revenue"


class GasLiftValveType(str, Enum):
    CASING_SENSITIVE = "casing_sensitive"
    TUBING_SENSITIVE = "tubing_sensitive"
    PROPORTIONAL = "proportional"


class BrineModel(str, Enum):
    DEFAULT = "default"
    IAWPS = "iawps"


class SensitivityVariable(str, Enum):
    ESP_FREQUENCY = "esp_frequency"
    GOR = "gor"
    RESERVOIR_PRESSURE = "reservoir_pressure"
    WATER_CUT = "water_cut"
    SKIN = "skin"
    TUBING_DIAMETER = "tubing_diameter"
    LATERAL_LENGTH = "lateral_length"
    BOUNDARY_PRESSURE = "boundary_pressure"
    GLR_INJECTED = "glr_injected"
    GAS_LIFT_INJECTION_RATE = "gas_lift_injection_rate"
    PUMP_SPEED = "pump_speed"
    CGR = "cgr"
    WGR = "wgr"
    DILUENT_RATE = "diluent_rate"


class ExportFormat(str, Enum):
    EXCEL = "excel"
    CSV = "csv"
    JSON = "json"


# =============================================================================
# MBAL Enumerations
# =============================================================================


class ReservoirType(str, Enum):
    OIL = "oil"
    GAS = "gas"
    CONDENSATE = "condensate"
    GAS_CAP_OIL = "gas_cap_oil"


class AquiferModel(str, Enum):
    NO_AQUIFER = "no_aquifer"
    FETKOVICH = "fetkovich"
    CARTER_TRACY = "carter_tracy"
    POT = "pot"
    HURST_VAN_EVERDINGEN = "hurst_van_everdingen"


# =============================================================================
# GAP Enumerations
# =============================================================================


class OptimizationObjective(str, Enum):
    MAX_OIL = "max_oil"
    MAX_GAS = "max_gas"
    MAX_PRODUCTION = "max_production"
    MAX_REVENUE = "max_revenue"
    OIL_RATE_ONLY = "oil_rate_only"
    WATER_RATE_ONLY = "water_rate_only"
    GAS_PLUS_OIL = "gas_plus_oil"
    GROSS_HEATING_VALUE = "gross_heating_value"
    GAS_RATE_OIL_PREFERENCE = "gas_rate_oil_preference"
    MIN_ENERGY = "min_energy"


class GAPSystemType(str, Enum):
    PRODUCTION = "production"
    WATER_INJECTION = "water_injection"
    GAS_INJECTION = "gas_injection"
    GAS_LIFT_INJECTION = "gas_lift_injection"


class GAPPVTModel(str, Enum):
    BLACK_OIL = "black_oil"
    TRACKING = "tracking"
    FULLY_COMPOSITIONAL = "fully_compositional"
    BO_COMPOSITIONAL_LUMPING_DELUMPING = "bo_compositional_lumping_delumping"


class GAPPredictionMethod(str, Enum):
    PRESSURE_ONLY = "pressure_only"
    PRESSURE_AND_TEMPERATURE = "pressure_and_temperature"
    PRESSURE_AND_TEMPERATURE_GRADIENT = "pressure_and_temperature_gradient"


class GAPTemperatureModel(str, Enum):
    ROUGH_APPROXIMATION = "rough_approximation"
    IMPROVED_APPROXIMATION = "improved_approximation"
    CALCULATE_HEAT_TRANSFER = "calculate_heat_transfer"


class GAPSolverMode(str, Enum):
    NO_OPTIMISATION = "no_optimisation"
    RULE_BASED = "rule_based"
    OPTIMISE_ALL_CONSTRAINTS = "optimise_all_constraints"
    OPTIMISE_POTENTIAL_CONSTRAINTS = "optimise_potential_constraints"


class GAPWellType(str, Enum):
    GAS_PRODUCER = "gas_producer"
    OIL_PRODUCER_NO_LIFT = "oil_producer_no_lift"
    OIL_PRODUCER_GAS_LIFTED = "oil_producer_gas_lifted"
    OIL_PRODUCER_ESP = "oil_producer_esp"
    OIL_PRODUCER_PCP = "oil_producer_pcp"
    OIL_PRODUCER_HSP = "oil_producer_hsp"
    OIL_PRODUCER_JET_PUMP = "oil_producer_jet_pump"
    OIL_PRODUCER_SRP = "oil_producer_srp"
    OIL_PRODUCER_DILUENT = "oil_producer_diluent"
    RETROGRADE_CONDENSATE = "retrograde_condensate"
    WATER_INJECTOR = "water_injector"
    GAS_INJECTOR = "gas_injector"
    WATER_PRODUCER = "water_producer"
    LIQUID_INJECTOR = "liquid_injector"
    CBM_ESP = "cbm_water_producer_esp"
    CBM_PCP = "cbm_water_producer_pcp"


class GAPWellModel(str, Enum):
    VLP_IPR_INTERSECTION = "vlp_ipr_intersection"
    PC_INTERPOLATION = "pc_interpolation"
    OUTFLOW_ONLY_VLP = "outflow_only_vlp"
    OUTFLOW_ONLY_PROSPER = "outflow_only_prosper"


class GAPIPRType(str, Enum):
    STRAIGHT_LINE_VOGEL = "straight_line_vogel"
    PER_PHASE = "per_phase"
    FORCHHEIMER = "forchheimer"
    FORCHHEIMER_PSEUDO_PRESSURE = "forchheimer_pseudo_pressure"
    C_AND_N = "c_and_n"
    TABLE_LOOKUP = "table_lookup"


class GAPPipeCorrelation(str, Enum):
    PETROLEUM_EXPERTS_2 = "Petroleum_Experts_2"
    PETROLEUM_EXPERTS_4 = "Petroleum_Experts_4"
    PETROLEUM_EXPERTS_5 = "Petroleum_Experts_5"
    BEGGS_AND_BRILL = "Beggs_and_Brill"
    OLGAS_2P = "OLGAS_2P"
    OLGAS_3P = "OLGAS_3P"
    HYDRO_2P = "Hydro_2P"
    HYDRO_3P = "Hydro_3P"
    HAGEDORN_BROWN = "Hagedorn_Brown"
    DUNS_ROS = "Duns_Ros"
    GRE_MODIFIED = "GRE_Modified"


class GAPPipeModel(str, Enum):
    GAP_INTERNAL_CORRELATIONS = "gap_internal_correlations"
    LIFT_CURVES = "lift_curves"
    PROSPER_ONLINE = "prosper_online"


class GAPSeparatorType(str, Enum):
    PRODUCTION_SEPARATOR = "production_separator"
    WATER_INJECTION_MANIFOLD = "water_injection_manifold"
    GAS_INJECTION_MANIFOLD = "gas_injection_manifold"
    STEAM_INJECTION_MANIFOLD = "steam_injection_manifold"
    OIL_INJECTION_MANIFOLD = "oil_injection_manifold"
    LNG_PROCESS_PLANT = "lng_process_plant"


class GAPCompressorType(str, Enum):
    PERFORMANCE_CURVES = "performance_curves"
    FIXED_DP = "fixed_dp"
    FIXED_POWER = "fixed_power"
    RECIPROCATING = "reciprocating"
    MULTIPHASE = "multiphase"


class GAPTankModel(str, Enum):
    MATERIAL_BALANCE = "material_balance"
    DECLINE_CURVE = "decline_curve"
    EXTERNAL_SIMULATOR = "external_simulator"


class GAPDPControl(str, Enum):
    NONE = "none"
    FIXED_VALUE = "fixed_value"
    CALCULATED = "calculated"


class GAPScheduleEventType(str, Enum):
    CHANGE_CONSTRAINT = "change_constraint"
    START_WELL = "start_well"
    STOP_WELL = "stop_well"
    MASK = "mask"
    UNMASK = "unmask"
    BYPASS = "bypass"
    UNBYPASS = "unbypass"
    CHANGE_PRESSURE = "change_pressure"
    CHANGE_OPENSERVER_VARIABLE = "change_openserver_variable"
    CHANGE_VLP_FILE = "change_vlp_file"
    CHANGE_DIAMETER = "change_diameter"
    CHANGE_FIXED_RATE = "change_fixed_rate"
    CHANGE_INJECTION_RATE = "change_injection_rate"
