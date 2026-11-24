
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib

emails = [
    "you won a prize",
    "claim your free gift",
    "you have won money",
    "click here to get reward",
    "free offer limited time",
    "congratulations you are selected",
    "win a lottery now",
    "claim your cash prize",
    "hello how are you",
    "meeting scheduled tomorrow",
    "please check your assignment",
    "good morning friend",
    "let us meet today",
    "your project is completed",
    "please send me the report",
    "see you tomorrow"
]

labels = [
    1, 1, 1, 1, 1, 1, 1, 1,
    0, 0, 0, 0, 0, 0, 0, 0
]

# Split training and testing data
x_train, x_test, y_train, y_test = train_test_split(
    emails,
    labels,
    test_size=0.25,
    random_state=42,
    stratify=labels
)

# Create vectorizer
vectorizer = CountVectorizer()
x_train_vector = vectorizer.fit_transform(x_train)
x_test_vector = vectorizer.transform(x_test)

# Train model
model = MultinomialNB()
model.fit(x_train_vector, y_train)

# Test accuracy
predictions = model.predict(x_test_vector)
accuracy = accuracy_score(y_test, predictions)

# Save files
joblib.dump(model, "spam_model.pkl")
joblib.dump(vectorizer, "vectorizer.pkl")
joblib.dump(accuracy, "model_accuracy.pkl")

print("Model trained successfully!")
print("Test accuracy:", round(accuracy * 100, 2), "%")