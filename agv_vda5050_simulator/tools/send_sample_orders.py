from __future__ import annotations

import json
import time

import paho.mqtt.client as mqtt

BROKER = '127.0.0.1'
PORT = 1883
MANUFACTURER = 'tot'
INTERFACE_NAME = 'uagv'
MAJOR_VERSION = 'v3'


SAMPLE_ORDERS = {
    'AGV01': {
        'orderId': 'ORDER-AGV01-ACTIONS',
        'orderUpdateId': 1,
        'nodes': [
            {
                'nodeId': 'N1',
                'sequenceId': 0,
                'released': True,
                'actions': [
                    {
                        'actionId': 'AGV01-start-charge',
                        'actionType': 'startCharge',
                        'blockingType': 'HARD',
                    },
                ],
            },
            {
                'nodeId': 'N2',
                'sequenceId': 2,
                'released': True,
                'actions': [
                    {
                        'actionId': 'AGV01-stop-charge-before-pick',
                        'actionType': 'stopCharge',
                        'blockingType': 'HARD',
                    },
                    {
                        'actionId': 'AGV01-pick-box',
                        'actionType': 'pick',
                        'blockingType': 'HARD',
                        'actionParameters': [
                            {'key': 'loadId', 'value': 'BOX-AGV01'},
                            {'key': 'loadType', 'value': 'carton'},
                        ],
                    },
                ],
            },
            {
                'nodeId': 'N3',
                'sequenceId': 4,
                'released': True,
                'actions': [
                    {
                        'actionId': 'AGV01-drop-box',
                        'actionType': 'drop',
                        'blockingType': 'HARD',
                    },
                ],
            },
        ],
        'edges': [
            {'edgeId': 'E1', 'sequenceId': 1, 'released': True, 'startNodeId': 'N1', 'endNodeId': 'N2'},
            {'edgeId': 'E2', 'sequenceId': 3, 'released': True, 'startNodeId': 'N2', 'endNodeId': 'N3'},
        ],
    },
    'AGV02': {
        'orderId': 'ORDER-AGV02-PICK-DROP',
        'orderUpdateId': 1,
        'nodes': [
            {'nodeId': 'N3', 'sequenceId': 0, 'released': True},
            {
                'nodeId': 'N8',
                'sequenceId': 2,
                'released': True,
                'actions': [
                    {
                        'actionId': 'AGV02-pick-tray',
                        'actionType': 'pick',
                        'blockingType': 'HARD',
                        'actionParameters': [{'key': 'loadId', 'value': 'TRAY-AGV02'}],
                    },
                ],
            },
            {
                'nodeId': 'N13',
                'sequenceId': 4,
                'released': True,
                'actions': [
                    {
                        'actionId': 'AGV02-drop-tray',
                        'actionType': 'drop',
                        'blockingType': 'HARD',
                    },
                ],
            },
        ],
        'edges': [
            {'edgeId': 'E17', 'sequenceId': 1, 'released': True, 'startNodeId': 'N3', 'endNodeId': 'N8'},
            {'edgeId': 'E18', 'sequenceId': 3, 'released': True, 'startNodeId': 'N8', 'endNodeId': 'N13'},
        ],
    },
    'AGV03': {
        'orderId': 'ORDER-AGV03-CHARGE',
        'orderUpdateId': 1,
        'nodes': [
            {'nodeId': 'N5', 'sequenceId': 0, 'released': True},
            {
                'nodeId': 'N10',
                'sequenceId': 2,
                'released': True,
                'actions': [
                    {
                        'actionId': 'AGV03-start-charge',
                        'actionType': 'startCharge',
                        'blockingType': 'HARD',
                    },
                ],
            },
            {
                'nodeId': 'N15',
                'sequenceId': 4,
                'released': True,
                'actions': [
                    {
                        'actionId': 'AGV03-stop-charge',
                        'actionType': 'stopCharge',
                        'blockingType': 'SOFT',
                    },
                ],
            },
        ],
        'edges': [
            {'edgeId': 'E21', 'sequenceId': 1, 'released': True, 'startNodeId': 'N5', 'endNodeId': 'N10'},
            {'edgeId': 'E22', 'sequenceId': 3, 'released': True, 'startNodeId': 'N10', 'endNodeId': 'N15'},
        ],
    },
}


def main() -> None:
    client = mqtt.Client(client_id='sample_order_sender', protocol=mqtt.MQTTv311)
    client.connect(BROKER, PORT, 30)
    client.loop_start()
    for agv_id, order in SAMPLE_ORDERS.items():
        topic = f'{INTERFACE_NAME}/{MAJOR_VERSION}/{MANUFACTURER}/{agv_id}/order'
        client.publish(topic, json.dumps(order), qos=1)
        print(f'Sent {order["orderId"]} to {topic}')
        time.sleep(0.2)
    client.loop_stop()
    client.disconnect()


if __name__ == '__main__':
    main()
