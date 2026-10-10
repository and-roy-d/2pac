from typing import Any, ClassVar

from pyvisa.highlevel import ResourceManager
from pyvisa.resources.messagebased import MessageBasedResource
import qcodes.validators as vals
from lakeshore370_base import (
    BaseOutput,
    BaseSensorChannel,
    LakeshoreBase,
)
from qcodes.instrument import InstrumentChannel
from qcodes.parameters import Group, GroupParameter
from bisect import bisect


# There are 16 sensors channels (a.k.a. measurement inputs) in Model 372
_n_channels = 16


class LakeshoreModel370Output(InstrumentChannel):
    """An InstrumentChannel for control outputs (heaters) of Lakeshore Model 372"""

    MODES: ClassVar[dict[str, int]] = {
        "closed": 1,
        "zone": 2,
        "open_loop": 3,
        "off": 4,
    }
    POLARITIES: ClassVar[dict[str, int]] = {"unipolar": 0, "bipolar": 1}
    RANGES: ClassVar[dict[str, int]] = {
        "off": 0,
        "31.6uA": 1,
        "100uA": 2,
        "316uA": 3,
        "1mA": 4,
        "3.16mA": 5,
        "10mA": 6,
        "31.6mA": 7,
        "100mA": 8,
    }

    _input_channel_parameter_kwargs: ClassVar[dict[str, Any]] = {
        "get_parser": int,
        "vals": vals.Numbers(1, _n_channels),
    }

    def __init__(self, parent: "LakeshoreModel370", output_name: str) -> None:
        super().__init__(parent, output_name)

        self.add_parameter("out",
                           get_cmd="HTR?",
                           set_cmd="MOUT {}",
                           get_parser=float,
                           unit="%")
        self.add_parameter("mode",
                           val_mapping=self.MODES,
                           get_cmd="CMODE?",
                           set_cmd=f"CMODE {{}}")
        
        self.add_parameter("range",
                           val_mapping = self.RANGES,
                           get_cmd="HTRRNG?",
                           set_cmd="HTRRNG {}")

        # Add more parameters for CSET command
        # and redefine the corresponding group
        self.add_parameter(
            "channel",
            label="channel to control",
            vals=vals.Numbers(1, _n_channels),
            get_parser=int,
            parameter_class=GroupParameter,
        )
        self.add_parameter(
            "use_filter",
            label="Use filter for readings",
            docstring="Specifies controlling on unfiltered or filtered readings",
            val_mapping={True: 1, False: 0},
            parameter_class=GroupParameter,
        )
        self.add_parameter(
            "delay",
            label="Delay",
            unit="s",
            docstring="Delay in seconds for setpoint change during Autoscanning",
            vals=vals.Ints(0, 255),
            get_parser=int,
            parameter_class=GroupParameter,
        )
        self.output_group = Group(
            [
                self.channel,
                self.use_filter,
                self.delay,
            ],
            set_cmd=f"CSET {{channel}}, {{use_filter}}, {{delay}}, 1, 8, 50",
            get_cmd=f"CSET?",
        )
        self.add_parameter('P',
                               label='Proportional (closed-loop)',























































































































































































































































































        #     "(excitation on), or shunted "
        #     "(excitation off)",
        #     val_mapping={False: 0, True: 1},
        #     parameter_class=GroupParameter,
        # )
        # self.add_parameter(
        #     "units",
        #     label="Preferred units",
        #     docstring="Specifies the preferred units parameter "
        #     "for sensor readings and for the control "
        #     "setpoint (kelvin or ohms)",
        #     val_mapping={"kelvin": 1, "ohms": 2},
        #     parameter_class=GroupParameter,
        # )
        # self.output_group = Group(
        #     [
        #         self.excitation_mode,
        #         self.excitation_range_number,
        #         self.auto_range,
        #         self.range,
        #         self.current_source_shunted,
        #         self.units,
        #     ],
        #     set_cmd=f"INTYPE {self._channel}, "
        #     f"{{excitation_mode}}, "
        #     f"{{excitation_range_number}}, "
        #     f"{{auto_range}}, {{range}}, "
        #     f"{{current_source_shunted}}, "
        #     f"{{units}}",
        #     get_cmd=f"INTYPE? {self._channel}",
        # )


class LakeshoreModel370(LakeshoreBase):
    """
    QCoDeS driver for Lakeshore Model 370 Temperature Controller.

    Note that interaction with the control input (referred to as 'A' in the
    Computer Interface Operation section of the manual) is not implemented.
    """

    channel_name_command: ClassVar[dict[str, str]] = {
        f"ch{i:02}": str(i) for i in range(1, 1 + _n_channels)
    }
    input_channel_parameter_values_to_channel_name_on_instrument: ClassVar[
        dict[int, str]
    ] = {i: f"ch{i:02}" for i in range(1, 1 + _n_channels)}

    CHANNEL_CLASS = LakeshoreModel370Channel

    def __init__(self, name: str, address: str, **kwargs: Any) -> None:
        super().__init__(name, address, **kwargs)

        self.add_submodule("heater", LakeshoreModel370Output(self, output_name="heater"))

    def _open_resource(self, address: str, visalib: str | None) -> tuple[MessageBasedResource, str, ResourceManager]:
        # first call the existing _open_resource method
        resource, visabackend, resource_manager = super()._open_resource(address, visalib)
        # then set the odd communication settings that can't be passed by argument with the current api
        from pyvisa import constants
        resource.parity = constants.Parity.odd
        resource.data_bits = 7
        return resource, visabackend, resource_manager
    