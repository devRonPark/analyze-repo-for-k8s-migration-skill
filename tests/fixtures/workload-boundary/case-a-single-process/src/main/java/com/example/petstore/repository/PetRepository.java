package com.example.petstore.repository;

/** Code layer inside the single `Application` process -- not an independent runtime process. */
public class PetRepository {
    public String queryAll() {
        return "[]";
    }
}
