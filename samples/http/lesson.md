# HTTP Requests and Responses

**Objective:** Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.

**Estimated time:** 32 minutes

## Learning outcomes

- Explain the HTTP GET method
- Explain the HTTP POST method
- Distinguish between 2xx, 4xx, and 5xx response status categories

## Introduction: How Devices Talk on the Web (~1 min)

Every time you open a web browser, view a page, or fill out an online form, your device communicates across the internet using a structured protocol [S6], [S15]. Have you ever wondered what happens behind the scenes when you load a weather forecast or submit a sign-up form? [S5], [S15]

The web relies on a communication model where a client (like your web browser) sends a request to a remote server, and the server sends back a response [S5], [S15], [S16]. The standard protocol governing these exchanges is called the Hypertext Transfer Protocol, or HTTP [S6], [S15]. In this lesson, you will learn how HTTP methods specify your intent and how server response status codes report the outcome of your requests [S2], [S6], [S7].

## Understanding the HTTP GET Method (~2 min)

### What is HTTP?

Hypertext Transfer Protocol (HTTP) is a stateless application-level protocol designed for distributed, collaborative, hypertext information systems [S6]. It structures how requests and responses are formatted and transferred between clients and servers across the internet [S6], [S15]. An HTTP request message consists of a request line (containing the method and path), request headers, and an optional body [S5], [S14], [S16].

### The GET Method

The **GET** method is the primary mechanism of information retrieval on the web [S6]. When a client issues a GET request, it asks the server to transfer a representation of the specified resource [S2], [S6]. For example, when you navigate to a website or request the current weather for a specific city, your browser sends a GET request to retrieve that data [S5], [S15], [S16].

### Key Characteristics of GET

HTTP defines several formal characteristics for request methods [S2]:

*   **No Request Body:** Requests using GET should only retrieve data and should not contain request content or a body payload [S2], [S5], [S6]. You are requesting data from the specified endpoint without attaching payload content [S5].
*   **Safe:** GET is classified as a *safe* method [S1], [S2], [S6]. Safe methods are read-only operations that do not alter resources or cause side effects on the server [S1], [S2], [S6].
*   **Idempotent:** GET is *idempotent* [S1], [S2], [S6]. An idempotent method produces the same intended effect on the server whether it is executed once or multiple times consecutively [S1], [S6]. Calling a GET request repeatedly simply retrieves the current resource representation without altering server state [S1], [S2], [S6].
*   **Cacheable:** GET responses are defined as cacheable [S1], [S2], [S6]. Caching allows responses to be stored for future reuse to optimize performance [S6].

## Understanding the HTTP POST Method (~2 min)

### The POST Method

While GET retrieves data, the **POST** method submits an entity to the specified resource on the server [S1], [S2], [S6]. Sending a POST request often causes a change in state or side effects on the server [S1], [S2], [S6]. Common real-world uses of POST include adding a new user through a sign-up form, posting a message to a group or bulletin board, providing data from a form submission, or appending new data to a database [S1], [S5].

### Key Characteristics of POST

*   **Requires / Contains a Body:** Unlike GET, a POST request carries data inside a request body [S1], [S5]. The type of data in the body is declared using the `Content-Type` request header [S1].
*   **Form Encodings:** HTML forms typically submit data using POST [S1]. Common form encodings include `application/x-www-form-urlencoded` (where data is formatted as `key=value` pairs separated by `&`) and `multipart/form-data` (used for uploading files or submitting large blocks of data delineated by boundary strings) [S1]. Non-form calls (such as API fetch requests) can send JSON or other body formats [S1], [S5].
*   **Not Safe:** POST is **not safe** [S1], [S2]. Executing a POST request actively submits data to a server process, creating resources or modifying server state [S1], [S2], [S6].
*   **Not Idempotent:** POST is **not idempotent** [S1], [S2]. Calling identical POST requests multiple times may produce additional side effects [S1], [S6]. For example, submitting a POST order request twice could create two separate orders in the system [S1], [S5].
*   **Cacheability:** POST is generally not cacheable by default, unless the response explicitly includes freshness information and matching location headers [S1], [S2], [S6].

### Comparison Table: GET vs. POST

| Feature | HTTP GET | HTTP POST |
| :--- | :--- | :--- |
| **Primary Purpose** | Read / retrieve data [S2], [S5], [S6] | Submit data / create resource [S1], [S2], [S5], [S6] |
| **Has Request Body?** | No [S2], [S5], [S6] | Yes [S1], [S5] |
| **Safe?** | Yes (Read-only) [S1], [S2], [S6] | No (Causes side effects / state change) [S1], [S2], [S6] |
| **Idempotent?** | Yes (Repeated calls yield same state) [S1], [S2], [S6] | No (Repeated calls cause multiple effects) [S1], [S5], [S6] |
| **Cacheable?** | Yes [S1], [S2], [S6] | Only with explicit freshness info [S1], [S2], [S6] |

## HTTP Response Status Categories: 2xx, 4xx, and 5xx (~2 min)

### What is an HTTP Response Status Code?

When a server processes an HTTP request, it returns an HTTP response message [S5], [S14], [S16]. An HTTP response includes a protocol version, a status code, status text, response headers, and an optional response body [S5], [S14], [S16].

The **status code** is a 3-digit integer that signals the outcome of the request [S6], [S7]. The first digit of the status code defines the overall class or category of the response [S6], [S7].

### 2xx Category: Successful Responses

Status codes starting with **2** (2xx) indicate that the request was successfully received, understood, and accepted by the server [S6], [S7].

*   **200 OK:** Standard successful response indicating the request succeeded with no issues [S6], [S15], [S16].
*   **201 Created:** Indicates that the request was fulfilled and resulted in one or more new resources being created on the server [S6], [S16].
*   **204 No Content:** Indicates that the server successfully fulfilled the request, but there is no payload body to send in the response [S6], [S16].

### 4xx Category: Client Error Responses

Status codes starting with **4** (4xx) indicate a **Client Error** [S6], [S7]. This means the request contains bad syntax or cannot be fulfilled due to an issue on the client's side [S6], [S7], [S16].

*   **400 Bad Request:** Generic client error indicating the request is malformed or invalid [S6], [S7].
*   **401 Unauthorized:** The request lacks valid authentication credentials [S16].
*   **403 Forbidden:** The server understands the request but refuses to authorize it [S16].
*   **404 Not Found:** The requested resource or piece of content could not be found on the server [S6], [S15], [S16].

### 5xx Category: Server Error Responses

Status codes starting with **5** (5xx) indicate a **Server Error** [S6], [S7]. This means the client sent an apparently valid request, but the server failed to fulfill it due to an internal server issue [S6], [S7], [S16].

*   **500 Internal Server Error:** A generic error message indicating the server encountered an unexpected condition [S6], [S16].
*   **503 Service Unavailable:** The server is currently unable to handle the request, often due to maintenance or overload [S16].

### Summary of Status Classes

*   **1xx:** Informational (request received, continuing process) [S6], [S7].
*   **2xx:** Successful (request accepted and completed) [S6], [S7], [S16].
*   **3xx:** Redirection (further action needed to complete request) [S6], [S7].
*   **4xx:** Client Error (request problem / bad syntax / resource missing) [S6], [S7], [S16].
*   **5xx:** Server Error (server failed to fulfill valid request) [S6], [S7], [S16].

## Worked Examples: Analyzing Requests and Responses (~2 min)

### Example 1: Fetching Weather Data (GET Request)

**Scenario:** A client app requests the current weather report for a city [S5].

*   **Method Used:** `GET` [S5].
*   **Request Characteristics:** The client sends an HTTP GET request targeting `/v1/weather?city=Seattle` [S5]. It contains headers but no request body payload [S2], [S5], [S6].
*   **Server Response:** The server processes the request, locates the weather resource, and responds with a status code of `200 OK` and a JSON body containing the temperature data [S5], [S6], [S15], [S16].
*   **Analysis:** This is a safe, read-only operation categorized under the 2xx (Successful) response class [S1], [S2], [S6], [S7].

### Example 2: Submitting a Sign-up Form (POST Request)

**Scenario:** A user fills out a registration form on a website and clicks "Submit" [S1], [S5].

*   **Method Used:** `POST` [S1], [S5].
*   **Request Characteristics:** The browser packages the user's input (such as username and email) into the request body formatted as `application/x-www-form-urlencoded` [S1].
*   **Server Response:** The server processes the data, adds the new user to its database, and responds with `201 Created` [S1], [S6], [S16].
*   **Analysis:** Because a new user resource was created on the server, the operation is non-idempotent and returns a 2xx success code specifically denoting resource creation [S1], [S6], [S16].

### Example 3: Missing Page vs. Server Failure (4xx vs. 5xx)

**Scenario A:** A user types an incorrect web URL (`/profile-page-xyz`) into their browser address bar.

*   **Response Code:** `404 Not Found` [S6], [S15], [S16].
*   **Category:** 4xx Client Error [S6], [S7]. The request could not be fulfilled because the requested resource does not exist [S6], [S7], [S15].

**Scenario B:** A user submits a valid payment form, but the server's database service crashes while writing the transaction.

*   **Response Code:** `500 Internal Server Error` [S16].
*   **Category:** 5xx Server Error [S6], [S7]. The request was valid, but the server failed internally to process it [S6], [S7], [S16].

### Common Mistakes to Avoid

1.  **Do not attach a body to a GET request:** GET is designed to retrieve data without carrying request body payloads [S2], [S5], [S6].
2.  **Do not assume POST is safe or idempotent:** Calling a POST request repeatedly can create duplicate database records or orders [S1], [S5].
3.  **Do not confuse 4xx and 5xx errors:** 4xx errors mean the client sent a bad request or asked for a non-existent resource; 5xx errors mean the client request was valid, but the server encountered a failure [S6], [S7], [S16].

## Practice Activity: Scenario Classification (~5 min)

### Instructions
Read the following real-world web application scenarios. For each scenario, identify:
1. The appropriate HTTP method (`GET` or `POST`).
2. The expected response status category (`2xx`, `4xx`, or `5xx`).
3. A brief explanation justifying your choice.

---

#### Task 1
A mobile application requests a product catalog page from an e-commerce server to display items to a user.

*   **Method:**
*   **Status Category:**
*   **Explanation:**

#### Task 2
A user submits a new user account registration form containing a username and password.

*   **Method:**
*   **Status Category:**
*   **Explanation:**

#### Task 3
A user tries to open a document link, but the file was deleted from the server last week.

*   **Method:**
*   **Status Category:**
*   **Explanation:**

#### Task 4
A client sends a valid data request, but the server's backend process crashes due to an unexpected unhandled code exception.

*   **Method:**
*   **Status Category:**
*   **Explanation:**

---

### Solutions and Model Answers

*   **Task 1 Solution:**
    *   **Method:** `GET`
    *   **Status Category:** `2xx` (e.g., `200 OK`)
    *   **Explanation:** `GET` is used because the client is retrieving existing product data without submitting a body or changing server state [S2], [S5], [S6]. A successful retrieval returns a `2xx` status code [S6], [S7].
*   **Task 2 Solution:**
    *   **Method:** `POST`
    *   **Status Category:** `2xx` (e.g., `201 Created`)
    *   **Explanation:** `POST` is used to send user data inside the request body to create a new user entity on the server [S1], [S5]. Upon successful creation, the server responds with a `2xx` status code (such as `201 Created`) [S6], [S16].
*   **Task 3 Solution:**
    *   **Method:** `GET`
    *   **Status Category:** `4xx` (e.g., `404 Not Found`)
    *   **Explanation:** The client attempts to retrieve a document via `GET` [S2], [S6]. Because the requested resource no longer exists, the server returns a `4xx` client error code (`404 Not Found`) [S6], [S15], [S16].
*   **Task 4 Solution:**
    *   **Method:** `GET` (or `POST` depending on action)
    *   **Status Category:** `5xx` (e.g., `500 Internal Server Error`)
    *   **Explanation:** Although the request sent by the client was valid, the server crashed internally [S6], [S7]. Server-side failures are categorized under `5xx` server errors [S6], [S7], [S16].

## Recommended Video Lessons (~11 min)

To reinforce your understanding of HTTP requests, responses, and status code categories, watch the following video lessons:

1.  **What are HTTP requests?** (4.9 minutes) [S15]
    *   **URL:** https://www.youtube.com/watch?v=-Zea7GB2OwA
    *   **What to watch for:** Pay attention to how HTTP structures communication over TCP, how GET retrieves data while POST creates new resources, and how status codes like 200 and 404 signal results [S15].

2.  **HTTP Requests and Responses Explained in 5 Minutes** (5.0 minutes) [S16]
    *   **URL:** https://www.youtube.com/watch?v=vPpWgK2LqDI
    *   **What to watch for:** Note the structure of HTTP messages (request line, headers, body) and how response status codes are grouped into 2xx success, 4xx client errors, and 5xx server errors [S16].

- ▶ [What are HTTP requests?](https://www.youtube.com/watch?v=-Zea7GB2OwA) (4.9 min) — Explains how HTTP structures requests and responses, covering GET and POST methods along with common status codes like 200 and 404. [S15]
- ▶ [HTTP Requests and Responses Explained in 5 Minutes](https://www.youtube.com/watch?v=vPpWgK2LqDI) (5 min) — Provides a quick visual overview of HTTP message anatomy, GET and POST methods, and status code categories including 2xx, 4xx, and 5xx. [S16]

## Knowledge Check Instructions (~6 min)

Answer the following multiple-choice questions to test your understanding of GET, POST, and HTTP status code categories. Select the single best answer for each question.

1. What is the primary purpose of the HTTP GET method?
   - A) To retrieve or read data from a server without modifying resources
   - B) To create a new resource on the server
   - C) To submit sensitive form data in the request body
   - D) To delete an existing file from the host server
   - **Answer:** To retrieve or read data from a server without modifying resources — The GET method requests a representation of the specified resource and is used to retrieve data without creating or modifying resources on the server [S2], [S5], [S6].

2. Which characteristic correctly describes the HTTP GET method?
   - A) GET requests should not contain a request body and are safe and idempotent
   - B) GET requests are unsafe because they alter server database tables
   - C) GET requests must include a Content-Type header with a boundary string
   - D) GET requests are never cacheable under any circumstance
   - **Answer:** GET requests should not contain a request body and are safe and idempotent — HTTP GET requests are designed to retrieve data without a request body and are categorized as safe, idempotent, and cacheable [S1], [S2], [S5], [S6].

3. What happens when a client sends an HTTP POST request to a server?
   - A) It submits data to the server, often causing a change in state or side effects on the server
   - B) It retrieves a resource without allowing any body content in the request
   - C) It guarantees that sending multiple identical requests will produce zero side effects
   - D) It deletes the targeted resource from the server host database
   - **Answer:** It submits data to the server, often causing a change in state or side effects on the server — The POST method submits an entity to a specified resource, sending data to the server and often causing state changes or side effects [S1], [S2], [S6].

4. Why is the HTTP POST method classified as non-idempotent?
   - A) Successive identical POST requests may have additional effects, such as creating duplicate resources
   - B) POST requests are strictly read-only and cannot alter server resources
   - C) POST requests never carry a request body
   - D) POST requests always return a 404 Not Found status code
   - **Answer:** Successive identical POST requests may have additional effects, such as creating duplicate resources — Unlike idempotent methods, calling POST multiple times can result in additional side effects, such as creating multiple separate orders or records [S1], [S5].

5. A user tries to visit a web page, but receives a 404 status code. How is this response category classified?
   - A) 4xx indicates a Client Error, meaning the request contains bad syntax or cannot be fulfilled
   - B) 4xx indicates a Successful response, meaning the server processed the request correctly
   - C) 4xx indicates a Server Error, meaning the server crashed while trying to fulfill a valid request
   - D) 4xx indicates an Informational response, meaning the request is still continuing process
   - **Answer:** 4xx indicates a Client Error, meaning the request contains bad syntax or cannot be fulfilled — The 4xx class of status codes indicates a client error, such as a 404 Not Found when a requested resource cannot be fulfilled [S6], [S7], [S15], [S16].

6. How do 2xx, 4xx, and 5xx response status categories differ from one another?
   - A) 2xx indicates success, 4xx indicates a client error, and 5xx indicates a server error
   - B) 2xx indicates a client error, 4xx indicates a server error, and 5xx indicates success
   - C) 2xx indicates a redirection, 4xx indicates success, and 5xx indicates an informational response
   - D) 2xx indicates a server error, 4xx indicates an informational response, and 5xx indicates a client error
   - **Answer:** 2xx indicates success, 4xx indicates a client error, and 5xx indicates a server error — The first digit defines the status category: 2xx represents successful responses, 4xx represents client error responses, and 5xx represents server error responses [S6], [S7], [S16].

## Lesson Summary (~1 min)

Here are the key takeaways from this lesson:

1.  **HTTP GET Method:** Used strictly to read or retrieve data representation from a server [S2], [S5], [S6]. GET requests should not contain request bodies and are safe, idempotent, and cacheable [S1], [S2], [S5], [S6].
2.  **HTTP POST Method:** Used to submit data entities to a server, often creating resources or causing state changes [S1], [S2], [S5], [S6]. POST requests carry data in a request body, are not safe, and are not idempotent [S1], [S2], [S5].
3.  **Status Code Categories:** The first digit of a 3-digit HTTP status code defines its class [S6], [S7]:
    *   **2xx (Successful):** The request was received, understood, and accepted (e.g., 200 OK, 201 Created) [S6], [S7], [S16].
    *   **4xx (Client Error):** The request contains bad syntax or cannot be fulfilled due to a client-side issue (e.g., 404 Not Found) [S6], [S7], [S15], [S16].
    *   **5xx (Server Error):** The server failed to fulfill an apparently valid request due to an internal server issue (e.g., 500 Internal Server Error) [S6], [S7], [S16].

## References

- **[S1]** POST request method - HTTP | MDN — developer.mozilla.org. <https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/POST> _Web, reliability tier 1_
- **[S2]** HTTP request methods - HTTP | MDN — developer.mozilla.org. <https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods> _Web, reliability tier 1_
- **[S5]** HTTP Request Methods – Get vs Put vs Post Explained with Code Examples — freecodecamp.org. <https://www.freecodecamp.org/news/http-request-methods-explained> _Web, reliability tier 3_
- **[S6]** RFC 7231 - Hypertext Transfer Protocol †HTTP/1.1 — law.resource.org. <https://law.resource.org/pub/us/cfr/regulations.gov.aera.case/gov.uscourts.dcd.166323.70.72.pdf> _Web, reliability tier 1_
- **[S7]** HTTP Error Codes in Real-World APIs: More Than Just 400 and 500 — medium.com. <https://medium.com/@burakkilic408/http-error-codes-in-real-world-apis-more-than-just-400-and-500-6d01c402290e> _Web, reliability tier 4_
- **[S14]** The Http and the Web | Http Explained | Request-Response Cycle — The TechCave. <https://www.youtube.com/watch?v=eesqK59rhGA> _Video, reliability tier 4_
- **[S15]** What are HTTP requests? — Codecademy. <https://www.youtube.com/watch?v=-Zea7GB2OwA> _Video, reliability tier 3_
- **[S16]** HTTP Requests and Responses Explained in 5 Minutes — Web Zone. <https://www.youtube.com/watch?v=vPpWgK2LqDI> _Video, reliability tier 4_

## Further reading

_Suggested books. Only their catalogue details and publisher descriptions were reviewed; they were not used as evidence for this lesson._

- HTTP Pocket Reference: Hypertext Transfer Protocol — Clinton Wong (2000). <https://play.google.com/store/books/details?id=dOIlEeG1v4UC>
- Learning Http/2: A Practical Guide for Beginners — Stephen Ludin, Javier Garza (2017). <https://books.google.com/books/about/Learning_Http_2.html?hl=&id=M0LgswEACAAJ>
- HTTP: The Definitive Guide: The Definitive Guide — David Gourley, Brian Totty, Marjorie Sayer, Anshu Aggarwal, Sailu Reddy (2002). <https://play.google.com/store/books/details?id=qEoOl9bcV_cC>
- Web Protocols and Practice: HTTP/1.1, Networking Protocols, Caching, and Traffic Measurement — Balachander Krishnamurthy, Jennifer Rexford (2001). <https://books.google.com/books/about/Web_Protocols_and_Practice.html?hl=&id=g_1SAAAAMAAJ>
- Hypertext Transfer Protocol HTTP/1.0 Specifications: 24-Apr-1998 — iUniverse (1999). <https://books.google.com/books/about/Hypertext_Transfer_Protocol_HTTP_1_0_Spe.html?hl=&id=IgNHAAAAYAAJ>
