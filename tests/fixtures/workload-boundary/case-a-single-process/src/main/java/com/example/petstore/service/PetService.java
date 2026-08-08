package com.example.petstore.service;

import com.example.petstore.repository.PetRepository;

/** Code layer inside the single `Application` process -- not an independent runtime process. */
public class PetService {
    private final PetRepository petRepository;

    public PetService(PetRepository petRepository) {
        this.petRepository = petRepository;
    }

    public String findAll() {
        return petRepository.queryAll();
    }
}
