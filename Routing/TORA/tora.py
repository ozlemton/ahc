import os
import sys
import time
from enum import Enum
from threading import Lock
from typing import Dict, Tuple

sys.path.insert(0, os.getcwd())

import matplotlib.pyplot as plt
import networkx as nx
from Ahc import (
    ComponentModel,
    ComponentRegistry,
    ConnectorTypes,
    Event,
    EventTypes,
    GenericMessage,
    GenericMessageHeader,
    GenericMessagePayload,
    Topology,
)
from Channels.Channels import P2PFIFOPerfectChannel
from LinkLayers.GenericLinkLayer import LinkLayer
from NetworkLayers.AllSeeingEyeNetworkLayer import AllSeingEyeNetworkLayer

registry = ComponentRegistry()


# define your own message types
class ApplicationLayerMessageTypes(Enum):
    UPD = "UPDATE"
    CLR = "CLEAR"
    QRY = "QUERY"


class Height:
    def __init__(self, tau, oid, r, delta, i):
        self.tau = tau
        self.oid = oid
        self.r = r
        self.delta = delta
        self.i = i


# define your own message header structure
class ApplicationLayerMessageHeader(GenericMessageHeader):
    pass


# define your own message payload structure
class ApplicationLayerMessagePayload(GenericMessagePayload):
    pass


class ApplicationLayerQueryMessagePayload(GenericMessagePayload):
    did: int

    def __init__(self, did: int):
        self.did = did


class ApplicationLayerUpdateMessagePayload(GenericMessagePayload):
    did: int
    height: Height
    link_reversal: bool

    def __init__(self, did: int, height: Height, link_reversal: bool):
        self.did = did
        self.height = height
        self.link_reversal = link_reversal


class TORAApplicationLayerComponent(ComponentModel):
    def __init__(self, componentname, componentinstancenumber):
        super().__init__(componentname, componentinstancenumber)
        self.neighbors = Topology().G.neighbors(componentinstancenumber)

        self.height: Height = Height(
            None, None, None, None, self.componentinstancenumber
        )

        self.last_upd: int = 0
        self.rr: bool = 0
        self.N: Dict[int, Tuple[Height, int]] = {}
        self.lock = Lock()

    def on_init(self, eventobj: Event):
        print(f"Initializing {self.componentname}.{self.componentinstancenumber}")

    def on_message_from_bottom(self, eventobj: Event):
        with self.lock:
            # try:
            applmessage = eventobj.eventcontent
            hdr = applmessage.header
            payload: GenericMessagePayload = applmessage.payload
            print(
                f"Node-{self.componentinstancenumber} says Node-{hdr.messagefrom} has sent {hdr.messagetype} message"
            )
            if hdr.messagetype == ApplicationLayerMessageTypes.QRY:
                self.handle_qry(payload.did, hdr.messagefrom)
            elif hdr.messagetype == ApplicationLayerMessageTypes.UPD:
                self.handle_upd(
                    payload.did, hdr.messagefrom, payload.height, payload.link_reversal
                )
            # except AttributeError:
            # print("Attribute Error")

    def handle_qry(self, did: int, fromid: int):
        downstream_links = self.get_downstream_links()

        if len(downstream_links) == 0:
            if self.rr == 0:
                self.broadcast_qry(did)
            else:
                pass
        elif self.height.delta is None:
            min_height = self.get_minimum_height_between_neighbours()
            self.height = Height(
                min_height.tau,
                min_height.oid,
                min_height.r,
                min_height.delta + 1,
                self.componentinstancenumber,
            )
            self.broadcast_upd(did, False)
        elif fromid in self.N and self.N[fromid][1] > self.last_upd:
            self.broadcast_upd(did, False)
        else:
            pass

    def handle_upd(self, did: int, from_id: int, height: Height, link_reversal: bool):
        self.set_neighbour_height(from_id, height)

        if link_reversal:
            pass
        else:
            if self.rr == 1:
                min_height = self.get_minimum_height_between_neighbours()
                self.height = Height(
                    min_height.tau,
                    min_height.oid,
                    min_height.r,
                    min_height.delta + 1,
                    self.componentinstancenumber,
                )
                self.rr = 0
                self.broadcast_upd(did, False)
            else:
                downstream_links = self.get_downstream_links()
                if len(downstream_links) == 0:
                    self.maintenance_case_1(did)
                    pass

    def maintenance_case_1(self, did: int):
        upstream_links = self.get_upstream_links()

        if len(upstream_links) == 0:
            self.height = (None, None, None, None, self.componentinstancenumber)
        else:
            self.height = (
                time.time(),
                self.componentinstancenumber,
                0,
                0,
                self.componentinstancenumber,
            )

        self.broadcast_upd(did, True)

    def maintenance_case_2(self, did: int):
        upstream_links = self.get_upstream_links()

        pass

    def maintenance_case_3(self, did: int):
        upstream_links = self.get_upstream_links()

        pass

    def maintenance_case_4(self, did: int):
        self.height = Height(None, None, None, None, self.componentinstancenumber)

    def maintenance_case_5(self, did: int):
        upstream_links = self.get_upstream_links()

        pass

    def get_minimum_height_between_neighbours(self) -> Height:
        downstream_links = self.get_downstream_links()
        min_height = downstream_links[list(downstream_links)[0]][0]
        min_height_delta = min_height.delta

        for i in list(downstream_links):
            downstream_link = downstream_links[i]

            if min_height_delta > downstream_link[0].delta + 1:
                min_height = downstream_link[0]
                min_height_delta = downstream_link[0].delta + 1

        return min_height

    def get_downstream_links(self):
        height_delta = 100000 if self.height.delta is None else self.height.delta
        return dict(
            filter(lambda link: link[1][0].delta < height_delta, list(self.N.items()))
        )

    def get_upstream_links(self):
        height_delta = -1 if self.height.delta is None else self.height.delta
        return dict(
            filter(lambda link: link[1][0].delta > height_delta, list(self.N.items()))
        )

    def broadcast_qry(self, did: int):
        self.rr = 1
        self.broadcast(
            ApplicationLayerQueryMessagePayload(did), ApplicationLayerMessageTypes.QRY
        )

    def broadcast_upd(self, did: int, link_reversal: bool):
        self.last_upd = time.time()
        self.broadcast(
            ApplicationLayerUpdateMessagePayload(did, self.height, link_reversal),
            ApplicationLayerMessageTypes.UPD,
        )

    def broadcast(
        self, payload: GenericMessagePayload, t: ApplicationLayerMessageTypes
    ):
        for destination in self.neighbors:
            hdr = ApplicationLayerMessageHeader(
                t,
                self.componentinstancenumber,
                destination,
            )
            msg = GenericMessage(hdr, payload)
            self.send_down(Event(self, EventTypes.MFRT, msg))

    def set_height(self, height: Height):
        self.height = height

        for destination_neighbour in self.neighbors:
            Topology().nodes[destination_neighbour].set_neighbour_height(
                self.componentinstancenumber, height
            )

    def set_neighbour_height(self, j: int, height: Height):
        self.N[j] = (height, time.time())


class TORANode(ComponentModel):
    def __init__(self, componentname, componentid):
        # SUBCOMPONENTS
        self.appllayer = TORAApplicationLayerComponent("ApplicationLayer", componentid)
        self.netlayer = AllSeingEyeNetworkLayer("NetworkLayer", componentid)
        self.linklayer = LinkLayer("LinkLayer", componentid)
        # self.failuredetect = GenericFailureDetector("FailureDetector", componentid)

        # CONNECTIONS AMONG SUBCOMPONENTS
        self.appllayer.connect_me_to_component(ConnectorTypes.DOWN, self.netlayer)
        # self.failuredetect.connectMeToComponent(PortNames.DOWN, self.netlayer)
        self.netlayer.connect_me_to_component(ConnectorTypes.UP, self.appllayer)
        # self.netlayer.connectMeToComponent(PortNames.UP, self.failuredetect)
        self.netlayer.connect_me_to_component(ConnectorTypes.DOWN, self.linklayer)
        self.linklayer.connect_me_to_component(ConnectorTypes.UP, self.netlayer)

        # Connect the bottom component to the composite component....
        self.linklayer.connect_me_to_component(ConnectorTypes.DOWN, self)
        self.connect_me_to_component(ConnectorTypes.UP, self.linklayer)

        super().__init__(componentname, componentid)

    def on_init(self, eventobj: Event):
        print(f"Initializing {self.componentname}.{self.componentinstancenumber}")

    def on_message_from_top(self, eventobj: Event):
        self.send_down(Event(self, EventTypes.MFRT, eventobj.eventcontent))

    def on_message_from_bottom(self, eventobj: Event):
        self.send_up(Event(self, EventTypes.MFRB, eventobj.eventcontent))

    def init_route_creation(self, did: int):
        self.appllayer.handle_qry(did, self.componentinstancenumber)

    def set_height(self, height: Height):
        self.appllayer.set_height(height)

    def set_neighbour_height(self, j: int, height: Height):
        self.appllayer.set_neighbour_height(j, height)


def main():
    # G = nx.Graph()
    # G.add_nodes_from([1, 2])
    # G.add_edges_from([(1, 2)])
    # nx.draw(G, with_labels=True, font_weight='bold')
    # plt.draw()
    G = nx.random_geometric_graph(5, 0.5)
    nx.draw(G, with_labels=True, font_weight="bold")
    plt.draw()

    topo = Topology()
    topo.construct_from_graph(G, TORANode, P2PFIFOPerfectChannel)
    topo.start()

    destination_id = 2
    source_id = 0

    destination_height: Height = Height(0, 0, 0, 0, destination_id)
    topo.nodes[destination_id].set_height(destination_height)

    topo.nodes[source_id].init_route_creation(destination_id)

    plt.show()

    while True:
        pass


if __name__ == "__main__":
    main()
