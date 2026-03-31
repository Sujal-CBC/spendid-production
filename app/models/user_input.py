from pydantic import BaseModel

class NewData(BaseModel):
    zipcode: str | None = None
    age: int | None = None
    number_of_people: int | None = None
    has_house: bool | None = None
    salary: int | None = None
    is_net_salary: bool | None = None
    past_credit_debt: float | None = None
    student_loan: float | None = None
    other_debt: float | None = None

class UserInput(BaseModel):
    session_id: str | None = None
    message: str
    new_data: NewData