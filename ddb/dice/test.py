from ddb.dice import RollRequest

roll = {
    "action": "custom",
    "rolls": [
        {
            "diceNotation": {
                "set": [
                    {
                        "dice": [
                            {
                                "dieType": "d20",
                                "dieValue": 15
                            },
                            {
                                "dieType": "d20",
                                "dieValue": 2
                            },
                            {
                                "dieType": "d20",
                                "dieValue": 13
                            },
                            {
                                "dieType": "d20",
                                "dieValue": 18
                            },
                            {
                                "dieType": "d20",
                                "dieValue": 10
                            }
                        ],
                        "count": 5,
                        "dieType": "d20",
                        "operation": 0
                    },
                    {
                        "dice": [
                            {
                                "dieType": "d4",
                                "dieValue": 4
                            },
                            {
                                "dieType": "d4",
                                "dieValue": 3
                            },
                            {
                                "dieType": "d4",
                                "dieValue": 4
                            }
                        ],
                        "count": 3,
                        "dieType": "d4",
                        "operation": 0
                    }
                ],
                "constant": 0
            },
            "rollType": "roll",
            "rollKind": "",
            "result": {
                "constant": 0,
                "values": [
                    15,
                    2,
                    13,
                    18,
                    10,
                    4,
                    3,
                    4
                ],
                "total": 69
            }
        }
    ],
    "context": {
        "entityId": "23783915",
        "entityType": "character"
    },
    "rollId": "9b20bfce-2641-4eb2-8fec-d4e44c6b4241"
}

if __name__ == '__main__':
    rr = RollRequest.from_dict(roll)
    d20_ast = rr.rolls[0].dice_notation.d20_ast()
    print(f"ast: {d20_ast}")
    print(rr.rolls[0].to_d20())
