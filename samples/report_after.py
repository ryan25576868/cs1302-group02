"""Build a one-line summary from a list of scores."""


def average(scores):
    return sum(scores) / len(scores)


def letter_grade(average):
    if average >= 90:
        return "A"
    if average >= 80:
        return "B"
    if average >= 70:
        return "C"
    return "F"


def summarize(scores):
    if not scores:
        return "no scores yet"
    mean = average(scores)
    return f"{len(scores)} scores, average {mean:.1f}, grade {letter_grade(mean)}"


if __name__ == "__main__":
    print(summarize([88, 92, 79]))
