from typing import NotRequired, TypedDict, List

Age = TypedDict("Age", {"from": int, "to": int})


class SearchCriteria(TypedDict):
    group: int
    userSex: str
    peerSex: str
    userAge: NotRequired[Age]
    peerAges: NotRequired[List[Age]]
