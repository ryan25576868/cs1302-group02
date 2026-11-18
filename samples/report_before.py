"""Build a one-line summary from a list of scores."""


def summarize(scores):
    if not scores:
        return "no scores yet"
    total = 0
    for score in scores:
        total += score
    average = total / len(scores)
    if average >= 90:
        grade = "A"
    elif average >= 80:
        grade = "B"
    elif average >= 70:
        grade = "C"
    else:
        grade = "F"
    return f"{len(scores)} scores, average {average:.1f}, grade {grade}"


if __name__ == "__main__":
    print(summarize([88, 92, 79]))
